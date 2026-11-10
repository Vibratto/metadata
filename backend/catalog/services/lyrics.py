"""Track lyrics, stored in an ``.lrc`` file next to the audio.

Players such as Navidrome read an ``.lrc`` named after the audio file before any embedded
lyrics. It works the same for every audio format and can be replaced without rewriting
the audio.
"""

from pathlib import Path
from typing import cast

from catalog.models import Download, Track
from catalog.services.library import absolute, place
from catalog.services.tagging import tags_for
from integrations.lrclib import LrclibClient
from integrations.lrclib import Lyrics as LrclibLyrics
from integrations.ytmusic import YTMusicClient, YTMusicError
from proxies.routing import proxied_session


class LyricsFinder:
    """Finds a track's lyrics, preferring timed ones.

    Order: timed lyrics from LRCLIB, then whatever YouTube Music has (timed or not), then
    plain lyrics from LRCLIB.
    """

    def __init__(self, lrclib: LrclibClient, ytmusic: YTMusicClient) -> None:
        self._lrclib = lrclib
        self._ytmusic = ytmusic

    def find(self, track: Track) -> str | None:
        """Lyrics text for ``track``, or ``None`` when it has none or is instrumental.

        Raises:
            requests.RequestException: If LRCLIB fails.
            YTMusicError: If YouTube Music fails and LRCLIB had nothing to fall back on.
        """
        known = self._from_lrclib(track)
        if known and (known.synced or known.instrumental):
            return known.synced
        plain = known.plain if known else None
        if not track.video_id:
            return plain
        try:
            found = self._ytmusic.get_lyrics(track.video_id)
        except YTMusicError:
            if plain:
                return plain
            raise
        return found.text if found else plain

    def _from_lrclib(self, track: Track) -> LrclibLyrics | None:
        # LRCLIB matches within ±2 s of the duration; without one there is nothing to ask.
        if not track.duration:
            return None
        tags = tags_for(track)
        return self._lrclib.get(
            tags.title, ", ".join(tags.artists), tags.album or "", track.duration
        )


def lyrics_client() -> LyricsFinder:
    """Finder whose requests go out through the configured proxies."""
    session = proxied_session()
    return LyricsFinder(LrclibClient(session), YTMusicClient(session=session))


def lyrics_path(audio: Path) -> Path:
    return audio.with_suffix(".lrc")


def _copy_sibling_lyrics(track: Track, audio: Path) -> bool:
    """Copy the ``.lrc`` of another track of the same recording, if one has it.

    Lyrics belong to the recording, so they are looked up once, not once per release.
    """
    siblings = Download.objects.filter(
        track__in=Track.objects.filter(recording=track.recording_id).exclude(pk=track.pk)
    )
    for download in cast(list[Download], list(siblings.order_by("-pk"))):
        source = lyrics_path(absolute(download.file_path))
        if source.is_file():
            place(lyrics_path(audio), source.read_bytes())
            return True
    return False


def save_lyrics(track: Track, audio: Path, finder: LyricsFinder) -> bool:
    """Find the lyrics of ``track`` and store them next to ``audio``.

    Returns:
        ``True`` if the ``.lrc`` was written; instrumental and unknown tracks get no file.

    Raises:
        requests.RequestException: If LRCLIB fails.
        YTMusicError: If YouTube Music fails and there is no fallback.
        OSError: If the file cannot be written.
    """
    if _copy_sibling_lyrics(track, audio):
        return True
    text = finder.find(track)
    if not text:
        return False
    text = text.removeprefix("﻿").replace("\r\n", "\n")
    place(lyrics_path(audio), text.encode("utf-8"))
    return True
