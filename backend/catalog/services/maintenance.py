"""Catalogue maintenance operations.

Every operation reports what it finds and never deletes anything: retagging rewrites the
tags of files that exist, relocating moves files without overwriting, and missing files
are listed rather than removed. ``Download`` is append-only, so a moved file gets a new
row and each operation reads only the newest row of every track.
"""

import logging
import os
from pathlib import Path
from typing import Any, cast

import mutagen
import requests
from django.db.models import OuterRef, Q, Subquery
from django.utils.translation import gettext as _

from activity.services import log_activity
from catalog.models import Album, Artist, Download, DownloadLoudness
from catalog.services import lyrics, replaygain
from catalog.services.importing import FETCH_ERRORS, Importer, ytmusic_client
from catalog.services.library import (
    COVER,
    CoverFetcher,
    absolute,
    album_cover,
    download_cover,
    download_folder,
    ids_for,
    place,
    store_artist_image,
)
from catalog.services.problems import report
from catalog.services.tagging import tags_for
from integrations.audio import AudioError, render_path, write_tags
from integrations.ytmusic import YTMusicClient
from jobs import runner
from jobs.models import JobRun
from preferences.models import get_value

logger = logging.getLogger(__name__)

RETAG = "retag"
REPLAYGAIN = "replaygain"
RELOCATE = "relocate"
CHECK_FILES = "check_files"
COMPLETE_ARTISTS = "complete_artists"
LYRICS = "lyrics"
COMPLETE_ALBUMS = "complete_albums"

#: Every operation, in the order they run.
OPERATIONS = (
    RETAG,
    REPLAYGAIN,
    RELOCATE,
    CHECK_FILES,
    COMPLETE_ARTISTS,
    LYRICS,
    COMPLETE_ALBUMS,
)
#: What runs when none are picked. Moving the library around is opt-in.
DEFAULT_OPERATIONS = (RETAG, REPLAYGAIN, CHECK_FILES, COMPLETE_ARTISTS, LYRICS)
#: Operations that rewrite tags; they never run together with ``RELOCATE``.
TAG_WRITERS = (RETAG, REPLAYGAIN)


def _latest_downloads() -> list[Download]:
    """Newest download of each track.

    Older rows of a track point to where its file was before it was relocated.
    """
    newest = Download.objects.filter(track=OuterRef("track")).order_by("-pk").values("pk")[:1]
    # ``Download.objects`` is typed on the append-only base class; the cast keeps the model.
    return cast(
        list[Download],
        list(
            Download.objects.select_related("track__album")
            .filter(pk=Subquery(newest))
            .order_by("pk")
        ),
    )


def _cover(album: Album, covers: dict[int, bytes | None], fetch: CoverFetcher) -> bytes | None:
    """Album cover, downloaded once per run.

    A failed download raises and is not cached, so the file is skipped instead of being
    written without its cover.
    """
    if album.pk not in covers:
        covers[album.pk] = fetch(album.cover_url) if album.cover_url else None
    return covers[album.pk]


def retag_downloads(run: JobRun, fetch_cover: CoverFetcher = download_cover) -> dict[str, Any]:
    """Rewrite the tags of every downloaded file from the catalogue.

    Also stores the artist images that are missing or whose URL changed.

    Returns:
        How many files were retagged and how many failed.
    """
    downloads = _latest_downloads()
    covers: dict[int, bytes | None] = {}
    embed = get_value("tags.embed_cover")
    folder = download_folder()
    retagged = failed = 0
    for index, download in enumerate(downloads, start=1):
        if runner.should_stop(run):
            break
        path = absolute(download.file_path)
        runner.progress(run, index, len(downloads), path.name)
        if not path.is_file():
            failed += 1
            runner.problem(run, path.name, _("The file is missing."))
            continue
        try:
            cover = _cover(download.track.album, covers, fetch_cover) if embed else None
            write_tags(path, tags_for(download.track, cover=cover))
        except (AudioError, OSError, mutagen.MutagenError, requests.RequestException) as error:
            failed += 1
            report(run, path.name, error)
        else:
            retagged += 1
            store_artist_image(download.track, folder, fetch_cover)
    if retagged:
        log_activity(run.user, "catalog.download.retagged", detail={"count": retagged})
    return {"retagged": retagged, "failed": failed}


def replaygain_albums(run: JobRun) -> dict[str, Any]:
    """Measure the whole library again and rewrite its ReplayGain, album by album.

    Returns:
        Albums and files updated, and albums that failed.
    """
    summary = {"albums": 0, "files": 0, "failed": 0}
    if not get_value("replaygain.enabled"):
        runner.problem(run, "ReplayGain", _("It is turned off in the settings."))
        return summary
    albums = list(Album.objects.filter(tracks__download__isnull=False).distinct().order_by("pk"))
    for index, album in enumerate(albums, start=1):
        if runner.should_stop(run):
            break
        runner.progress(run, index, len(albums), album.title)
        try:
            files = replaygain.update_album(album, remeasure=True)
        except (AudioError, OSError, mutagen.MutagenError) as error:
            summary["failed"] += 1
            report(run, album.title, error)
        else:
            summary["albums"] += 1
            summary["files"] += files
    return summary


def _relocate(download: Download, source: Path, dest: Path, fetch_cover: CoverFetcher) -> None:
    """Move the audio and its ``.lrc``, and make sure the new folder has the cover.

    The cover is taken from the old folder when it is there, so most albums need no
    download.

    shortcut: ``os.replace`` needs both paths on one filesystem. That holds inside a
    single library folder; a library spread over several mounts reports the error.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, dest)
    source_lyrics = lyrics.lyrics_path(source)
    if source_lyrics.is_file() and not lyrics.lyrics_path(dest).exists():
        os.replace(source_lyrics, lyrics.lyrics_path(dest))
    cover_path = dest.parent / COVER
    if not cover_path.is_file():
        cover = album_cover(download.track.album, source.parent / COVER, fetch_cover)
        if cover:
            place(cover_path, cover)


def relocate_downloads(run: JobRun, fetch_cover: CoverFetcher = download_cover) -> dict[str, Any]:
    """Move every file to the path the naming template gives it, leaving tags alone.

    Tags are not touched because Navidrome keeps a track's id, favourites and play
    counts when a file is moved or retagged, but not when both happen in one scan.
    Nothing is overwritten. Each moved file gets a new ``Download`` row with its new
    path and the loudness already measured.

    Returns:
        Files moved, already in place, and failed.
    """
    folder = download_folder()
    template = get_value("download.name_template")
    downloads = _latest_downloads()
    moved = unchanged = failed = 0
    for index, download in enumerate(downloads, start=1):
        if runner.should_stop(run):
            break
        source = absolute(download.file_path)
        runner.progress(run, index, len(downloads), source.name)
        track = download.track
        try:
            relative = render_path(
                template, tags_for(track), ids_for(track), source.suffix.lstrip(".")
            )
        except (KeyError, ValueError) as error:
            failed += 1
            logger.warning("No path for %s: %s", source, error)
            runner.problem(run, source.name, _("The name template cannot name this file."))
            continue
        dest = folder / relative
        if dest == source:
            unchanged += 1
            continue
        if not source.is_file():
            failed += 1
            runner.problem(run, source.name, _("The file is missing."))
            continue
        if dest.exists():
            failed += 1
            runner.problem(run, source.name, _("Another file already has the name it should take."))
            continue
        try:
            _relocate(download, source, dest, fetch_cover)
        except OSError as error:
            failed += 1
            report(run, source.name, error)
            continue
        new = Download.objects.create(
            track=track,
            file_path=str(relative),
            audio_format=download.audio_format,
            source_url=download.source_url,
        )
        # Same audio, so the measurement still holds.
        stored = DownloadLoudness.objects.filter(download=download).first()
        if stored:
            DownloadLoudness.objects.create(download=new, lufs=stored.lufs, peak=stored.peak)
        store_artist_image(track, folder, fetch_cover)
        moved += 1
    if moved:
        log_activity(run.user, "catalog.download.relocated", detail={"count": moved})
    return {"moved": moved, "unchanged": unchanged, "failed": failed}


def check_download_files(run: JobRun) -> dict[str, Any]:
    """Check that every downloaded file is still on disk. Nothing is deleted.

    Returns:
        How many were checked, and the ids of the downloads whose file is missing.
    """
    downloads = _latest_downloads()
    missing: list[int] = []
    checked = 0
    for download in downloads:
        if runner.should_stop(run):
            break
        checked += 1
        path = absolute(download.file_path)
        runner.progress(run, checked, len(downloads), path.name)
        if not path.is_file():
            missing.append(download.pk)
            runner.problem(run, path.name, _("The file is missing."))
    return {"checked": checked, "missing": missing}


def complete_albums(run: JobRun, client: YTMusicClient | None = None) -> dict[str, Any]:
    """Create the tracks YouTube Music lists for each stored album and the catalogue lacks.

    Useful after tracks were deleted by mistake, or when a release gained tracks after
    it was imported. Blocked tracks stay out.

    Returns:
        Albums checked, tracks created, recordings reused and errors.
    """
    importer = Importer(run, client or ytmusic_client())
    albums = list(Album.objects.filter(ytmusic_id__isnull=False).order_by("pk"))
    checked = errors = 0
    for index, album in enumerate(albums, start=1):
        if runner.should_stop(run):
            break
        checked += 1
        runner.progress(run, index, len(albums), album.title)
        try:
            importer.complete_album(album)
        except FETCH_ERRORS as error:
            errors += 1
            report(run, album.title, error)
    return {
        "albums": checked,
        "tracks": importer.counts["tracks"],
        "reused_recordings": importer.counts["reused_recordings"],
        "errors": errors,
    }


def complete_artists(run: JobRun, client: YTMusicClient | None = None) -> dict[str, Any]:
    """Refresh the profile of artists that lack an image or audience figures.

    It follows the importer's rules: figures are refreshed, empty fields are filled in,
    nothing edited by hand is replaced and no music is imported.

    Returns:
        Artists reviewed, completed, unchanged and failed.
    """
    importer = Importer(run, client or ytmusic_client())
    artists = list(
        Artist.objects.filter(ytmusic_id__isnull=False)
        .filter(Q(image_url="") | Q(monthly_listeners__isnull=True, subscribers__isnull=True))
        .order_by("pk")
    )
    reviewed = completed = unchanged = errors = 0
    for index, artist in enumerate(artists, start=1):
        if runner.should_stop(run):
            break
        reviewed += 1
        runner.progress(run, index, len(artists), artist.name)
        before = (artist.image_url, artist.audience)
        try:
            importer.complete_artist(artist)
        except FETCH_ERRORS as error:
            errors += 1
            report(run, artist.name, error)
            continue
        if (artist.image_url, artist.audience) == before:
            unchanged += 1
        else:
            completed += 1
    return {"reviewed": reviewed, "completed": completed, "unchanged": unchanged, "errors": errors}


def fetch_missing_lyrics(run: JobRun) -> dict[str, Any]:
    """Look up the lyrics of every downloaded file that has no ``.lrc`` yet.

    Tracks without lyrics are asked for again on later runs, since both sources keep
    adding songs.

    Returns:
        Lyrics found, not found, and lookups that failed.
    """
    downloads = cast(
        list[Download], list(Download.objects.select_related("track__album").order_by("pk"))
    )
    pending = [
        (download.track, path)
        for download in downloads
        if (path := absolute(download.file_path)).is_file()
        and not lyrics.lyrics_path(path).exists()
    ]
    finder = lyrics.lyrics_client()
    found = not_found = failed = 0
    for index, (track, path) in enumerate(pending, start=1):
        if runner.should_stop(run):
            break
        runner.progress(run, index, len(pending), path.name)
        try:
            saved = lyrics.save_lyrics(track, path, finder)
        except (*FETCH_ERRORS, OSError) as error:
            failed += 1
            report(run, track.title, error)
            continue
        if saved:
            found += 1
        else:
            not_found += 1
    return {"found": found, "not_found": not_found, "failed": failed}
