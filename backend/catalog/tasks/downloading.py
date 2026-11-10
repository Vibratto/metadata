"""``download`` job: downloads the catalogue's pending tracks."""

import math
import time
from typing import Any

import mutagen
from django.utils.translation import gettext as _

from activity.services import log_activity
from catalog.models import Album, Download, Track
from catalog.services import lyrics, replaygain
from catalog.services.downloading import build_pool, download_track
from catalog.services.importing import FETCH_ERRORS
from catalog.services.library import absolute, download_folder
from integrations.audio import FORMATS, AudioError
from integrations.youtube import NoProxyAvailable, ProxyPool
from jobs import registry, runner
from jobs.models import JobRun, JobRunLine
from preferences.models import get_value

#: Seconds between checks for a stop request while waiting for a proxy.
STOP_CHECK_SECONDS = 1.0

INFO = JobRunLine.Level.INFO
WARNING = JobRunLine.Level.WARNING
ERROR = JobRunLine.Level.ERROR


def _wait_for_proxy(run: JobRun, seconds: float) -> bool:
    """Wait for a proxy to come off its cool-down.

    Returns:
        ``False`` if a stop request arrived while waiting.
    """
    runner.line(
        run,
        WARNING,
        _("Every proxy is cooling down: retrying in %(seconds)d s.")
        % {"seconds": math.ceil(seconds)},
    )
    waited = 0.0
    while waited < seconds:
        step = min(STOP_CHECK_SECONDS, seconds - waited)
        time.sleep(step)
        waited += step
        if runner.should_stop(run):
            return False
    return True


def _pending(params: dict[str, Any]) -> list[Track]:
    """The tracks the params ask for, leaving out those already downloaded.

    Raises:
        ValueError: Neither ``track_ids`` nor ``all_pending`` was given.
    """
    tracks = Track.objects.filter(download__isnull=True)
    if params.get("all_pending"):
        return list(tracks.select_related("album", "recording"))
    if params.get("track_ids"):
        return list(tracks.filter(pk__in=params["track_ids"]).select_related("album", "recording"))
    raise ValueError(_("Give either “track_ids” or “all_pending”."))


def _update_albums(run: JobRun, albums: list[Album]) -> None:
    """Recompute the album gain of every album that received tracks.

    It runs once all downloads are done, so each album is measured a single time with all
    its new tracks. A failure is reported; the files stay downloaded.
    """
    for album in albums:
        try:
            replaygain.update_album(album)
        except (AudioError, OSError, mutagen.MutagenError) as error:
            runner.line(
                run,
                WARNING,
                _("ReplayGain of “%(title)s”: %(error)s") % {"title": album.title, "error": error},
            )


def _download(run: JobRun, track: Track, pool: ProxyPool, **options: Any) -> Download | None:
    """Download ``track``, waiting and retrying while no proxy is free.

    Moving on to the next track would only fail that one too.

    Returns:
        The download, or ``None`` if a stop request arrived while waiting.
    """
    while True:
        try:
            return download_track(track, pool, **options)
        except NoProxyAvailable as busy:
            if not _wait_for_proxy(run, busy.retry_in):
                return None


@registry.register("download")
def download(run: JobRun, params: dict[str, Any]) -> dict[str, Any]:
    """Download tracks one by one; one failing does not stop the rest.

    A stop request is honoured between tracks.

    Args:
        run: Current run.
        params: ``{"track_ids": [...]}`` or ``{"all_pending": true}``.

    Returns:
        Summary with ``downloaded``, ``failed`` and ``skipped``.
    """
    fmt = get_value("download.format")
    if fmt not in FORMATS:
        raise ValueError(_("Unsupported download format: %(format)s") % {"format": fmt})
    folder = download_folder()
    template = get_value("download.name_template")
    tracks = _pending(params)
    requested = len(params.get("track_ids") or [])
    skipped = max(requested - len(tracks), 0)
    pool = build_pool()
    finder = lyrics.lyrics_client() if get_value("lyrics.enabled") else None
    downloaded = failed = 0
    albums: dict[int, Album] = {}
    for index, track in enumerate(tracks):
        if runner.should_stop(run):
            runner.line(run, WARNING, _("Stop requested."))
            break
        runner.progress(run, index, len(tracks), track.title)
        try:
            result = _download(run, track, pool, fmt=fmt, folder=folder, template=template)
        except Exception as error:  # noqa: BLE001  # one broken track must not stop the rest
            failed += 1
            runner.line(run, ERROR, f"{track.title}: {error}")
            continue
        if result is None:
            runner.line(run, WARNING, _("Stop requested."))
            break
        downloaded += 1
        albums.setdefault(track.album_id, track.album)
        runner.line(run, INFO, f"{track.title} → {result.file_path}")
        if finder is not None:
            try:
                lyrics.save_lyrics(track, absolute(result.file_path), finder)
            except (*FETCH_ERRORS, OSError) as error:
                # Lyrics are an extra: failing to get them never fails the download.
                runner.line(
                    run,
                    WARNING,
                    _("%(title)s: no lyrics: %(error)s") % {"title": track.title, "error": error},
                )
    else:
        runner.progress(run, len(tracks), len(tracks))
    if get_value("replaygain.enabled"):
        _update_albums(run, list(albums.values()))
    summary = {"downloaded": downloaded, "failed": failed, "skipped": skipped}
    log_activity(run.user, "catalog.download.finished", detail=summary)
    return summary
