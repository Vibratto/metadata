"""Import of a folder of music that is already on disk.

Each audio file is matched to a YouTube Music song through its tags (artist, title, album
and length). Whatever the catalogue lacks is imported with
:class:`~catalog.services.importing.Importer`, and the file is recorded as a ``Download``.
Files are never moved, renamed or retagged. A file already recorded under the same path
is skipped, so importing a folder twice changes nothing.

A file is linked only when the match is certain. Anything doubtful is reported with its
reason and left for the user to review.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mutagen
from django.utils.translation import gettext as _
from mutagen.easyid3 import EasyID3
from mutagen.easymp4 import EasyMP4Tags

from catalog.models import Download, Track
from catalog.services.importing import FETCH_ERRORS, Importer
from core.errors import UserError
from integrations import ytmusic as ytm
from integrations.audio import Tags
from integrations.ytmusic import YTMusicClient
from integrations.ytmusic.names import split_featured
from jobs import runner
from jobs.models import JobRun
from preferences.models import get_value

logger = logging.getLogger(__name__)

# The plural tag with one artist per value, as this application writes it. mutagen reads
# it from Vorbis comments already; ID3 and MP4 need it registered.
EasyID3.RegisterTXXXKey("artists", "ARTISTS")  # type: ignore[no-untyped-call]
EasyMP4Tags.RegisterFreeformKey("artists", "ARTISTS")  # type: ignore[no-untyped-call]

#: Extensions that are read; covers, playlists and the rest are ignored.
AUDIO_SUFFIXES = frozenset({".mp3", ".flac", ".opus", ".ogg", ".m4a"})

#: Seconds a file may differ from the song it is matched to.
DURATION_TOLERANCE = 3

# Reasons a file is not linked. The web interface translates them.
OUTSIDE = "outside"
UNREADABLE = "unreadable"
NO_TAGS = "no_tags"
NOT_FOUND = "not_found"
NOT_IN_CATALOG = "not_in_catalog"
LOOKUP_ERROR = "error"
ALREADY_DOWNLOADED = "already_downloaded"
AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class AudioFile:
    """What a file says about itself."""

    tags: Tags
    duration: float | None = None


def resolve_folder(root: Path, folder: str) -> Path:
    """Real path of ``folder`` inside ``root``.

    Resolving first means ``..`` and symbolic links are judged by where they lead, not
    by how they read.

    Raises:
        UserError: The folder is outside ``root`` or does not exist.
    """
    base = root.resolve()
    target = (base / folder).resolve()
    if not target.is_relative_to(base):
        raise UserError(
            _("The folder “%(folder)s” is outside the library folder.") % {"folder": folder}
        )
    if not target.is_dir():
        raise UserError(_("The folder “%(folder)s” does not exist.") % {"folder": folder})
    return target


def read_file(path: Path) -> AudioFile | None:
    """Tags and length of an audio file; ``None`` without a title, as nothing can match.

    Raises:
        mutagen.MutagenError: The file is damaged.
    """
    audio = mutagen.File(path, easy=True)
    if audio is None or not audio.tags:
        return None

    def first(key: str) -> str:
        values = audio.tags.get(key) or [""]
        return str(values[0]).strip()

    title = first("title")
    if not title:
        return None
    number = first("tracknumber").partition("/")[0]
    artists = [str(a) for a in audio.tags.get("artists") or audio.tags.get("artist") or ()]
    if len(artists) == 1 and "artists" not in audio.tags:
        # Like Navidrome: a lone ARTIST tag is split on the separators, ignoring case.
        separators = get_value("tags.artist_separators")
        artists = re.split("|".join(map(re.escape, separators)), artists[0], flags=re.IGNORECASE)
    tags = Tags(
        title=title,
        artists=tuple(a.strip() for a in artists if a.strip()),
        album=first("album") or None,
        track_number=int(number) if number.isdigit() else None,
    )
    return AudioFile(tags, getattr(audio.info, "length", None))


def _same(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and str(a).casefold() == str(b).casefold()


def _is_match(hit: ytm.SongHit, file: AudioFile) -> bool:
    """Whether a search result is certainly the song in the file.

    Title and main artist must be the same, ignoring case and "feat." mentions. When both
    lengths are known they must agree within a few seconds, which keeps live takes and
    extended versions apart.
    """
    tags = file.tags
    if split_featured(hit.title)[0].casefold() != split_featured(tags.title)[0].casefold():
        return False
    if tags.artists and not any(_same(a.name, tags.artists[0]) for a in hit.artists):
        return False
    if file.duration and hit.duration:
        return abs(hit.duration - file.duration) <= DURATION_TOLERANCE
    return True


def find_remote(client: YTMusicClient, file: AudioFile) -> ytm.SongHit | None:
    """The YouTube Music song that is certainly the one in the file, if there is one.

    Among certain matches, one on the album the file names wins.
    """
    tags = file.tags
    query = " ".join(filter(None, [tags.artists[0] if tags.artists else "", tags.title]))
    hits = [hit for hit in client.search_songs(query) if _is_match(hit, file)]
    on_album = [hit for hit in hits if _same(hit.album_title, tags.album)]
    return next(iter(on_album or hits), None)


def _catalog_tracks(hit: ytm.SongHit) -> list[Track]:
    """Catalogue tracks of that recording; one per release it appears on."""
    return list(Track.objects.filter(recording__video_id=hit.video_id).select_related("album"))


def _on_the_album_of(candidates: list[Track], tags: Tags) -> list[Track]:
    """The candidates on the album the file names.

    The track number only narrows further when the album title leaves several.
    """
    found = [t for t in candidates if _same(t.album.title, tags.album)]
    if len(found) > 1 and tags.track_number is not None:
        found = [t for t in found if t.track_number == tags.track_number] or found
    return found


class FolderImporter:
    """Links the audio files of a folder to the catalogue inside a job run.

    Args:
        run: Receives progress and log lines.
        client: Source of YouTube Music data.
        root: The library folder from the settings. Paths are stored relative to it,
            the same way the download job stores them.
    """

    def __init__(self, run: JobRun, client: YTMusicClient, root: Path) -> None:
        self.run = run
        self._client = client
        self._root = root
        self._importer = Importer(run, client)
        self.linked = 0
        self.already_linked = 0
        self.unlinked: list[dict[str, str]] = []

    def import_folder(self, folder: str) -> bool:
        """Walk ``folder`` and link every audio file in it.

        Returns:
            ``False`` if a stop request cut the run short.

        Raises:
            UserError: The folder is not valid; see :func:`resolve_folder`.
        """
        base = self._root.resolve()
        target = resolve_folder(self._root, folder)
        # ``rglob`` does not descend into linked folders; linked files are checked one by one.
        files = sorted(
            p for p in target.rglob("*") if p.suffix.lower() in AUDIO_SUFFIXES and p.is_file()
        )
        for index, path in enumerate(files):
            if runner.should_stop(self.run):
                return False
            relative = path.relative_to(base)
            runner.progress(self.run, index, len(files), str(relative))
            self._link(path, relative)
        runner.progress(self.run, len(files), len(files))
        return True

    @property
    def counts(self) -> dict[str, Any]:
        """Counters of what was imported into the catalogue and of the files."""
        return {
            **self._importer.counts,
            "linked": self.linked,
            "already_linked": self.already_linked,
            "unlinked": self.unlinked,
        }

    def _link(self, path: Path, relative: Path) -> None:
        """Link one file, or record why it was not linked."""
        stored = str(relative)
        if Download.objects.filter(file_path=stored).exists():
            self.already_linked += 1
            return
        if not path.resolve().is_relative_to(self._root.resolve()):
            self._skip(relative, OUTSIDE)
            return
        try:
            file = read_file(path)
        except mutagen.MutagenError:
            self._skip(relative, UNREADABLE)
            return
        if file is None:
            self._skip(relative, NO_TAGS)
            return
        try:
            track, reason = self._track_for(file)
        except FETCH_ERRORS as error:
            logger.warning("Looking up %s failed: %s", relative, error)
            self._skip(relative, LOOKUP_ERROR)
            return
        if track is None:
            self._skip(relative, reason)
            return
        # Maintenance works on the newest download of a track, so a second one would make
        # it forget the file the track already had.
        if Download.objects.filter(track=track).exists():
            self._skip(relative, ALREADY_DOWNLOADED)
            return
        Download.objects.create(
            track=track, file_path=stored, audio_format=path.suffix.lower().lstrip(".")
        )
        self.linked += 1

    def _track_for(self, file: AudioFile) -> tuple[Track | None, str]:
        """Catalogue track for the file, importing its album when the catalogue lacks it.

        Returns:
            The track, or ``None`` and the reason.
        """
        hit = find_remote(self._client, file)
        if hit is None:
            return None, NOT_FOUND
        candidates = _catalog_tracks(hit)
        found = _on_the_album_of(candidates, file.tags)
        if not found and hit.album_id and (not candidates or file.tags.album):
            self._importer.import_release(ytm.ReleaseRef(hit.album_id, hit.album_title or ""))
            candidates = _catalog_tracks(hit)
            found = _on_the_album_of(candidates, file.tags)
        found = found or candidates
        if len(found) > 1:
            # The recording is on several releases and the file does not say which.
            return None, AMBIGUOUS
        # Nothing after importing means the album or the track is blocked.
        return (found[0], "") if found else (None, NOT_IN_CATALOG)

    def _skip(self, relative: Path, reason: str) -> None:
        self.unlinked.append({"file": str(relative), "reason": reason})
