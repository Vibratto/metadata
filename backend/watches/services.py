"""New-release checks."""

import logging
from collections.abc import Iterator
from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone

from activity.services import log_activity
from catalog.models import Album, Artist, BlockedItem, Track
from catalog.services.importing import Importer, ytmusic_client
from integrations import ytmusic as ytm
from integrations.ytmusic import YTMusicClient
from jobs import runner
from jobs.models import JobRun
from jobs.registry import UnknownJobKind
from watches.models import Watch, WatchRun

logger = logging.getLogger(__name__)

DOWNLOAD_KIND = "download"


def new_releases(client: YTMusicClient, artist: Artist) -> Iterator[ytm.ReleaseRef]:
    """The artist's releases that are neither in the catalogue nor blocked."""
    if not artist.ytmusic_id:
        return
    known = set(Album.objects.filter(ytmusic_id__isnull=False).values_list("ytmusic_id", flat=True))
    known |= set(
        BlockedItem.objects.filter(kind=BlockedItem.Kind.ALBUM).values_list(
            "external_id", flat=True
        )
    )
    for release in client.get_artist(artist.ytmusic_id).releases:
        if release.id not in known:
            yield release


def _start_download(tracks: list[Track], user: User | None) -> str:
    """Start downloading the new tracks; return a note for the run when that fails.

    The check itself succeeded, so a download that cannot start is reported, not raised.
    """
    try:
        runner.start(DOWNLOAD_KIND, {"track_ids": [t.pk for t in tracks]}, user)
    except (UnknownJobKind, runner.JobAlreadyRunning) as error:
        return f"Download not started: {type(error).__name__}"
    return ""


def check_watch(watch: Watch, run: JobRun, client: YTMusicClient | None = None) -> WatchRun:
    """Check a watch for new releases and record the outcome in a ``WatchRun``.

    New releases go through the catalogue ``Importer``, which logs to ``run``. The
    ``WatchRun`` is written even when the check fails, and the next check is always
    rescheduled, so a broken watch is retried at its own pace rather than on every pass.
    """
    client = client or ytmusic_client()
    importer = Importer(run, client)
    user = run.user
    started = timezone.now()
    tracks: list[Track] = []
    detail = ""
    status = WatchRun.Status.SUCCEEDED
    try:
        for artist in watch.artists.order_by("watch_entries__position"):
            for release in new_releases(client, artist):
                tracks += importer.try_import_release(release)
        if watch.auto_download and tracks:
            detail = _start_download(tracks, user)
    except Exception as error:
        logger.exception("Checking watch %s failed", watch.pk)
        status, detail = WatchRun.Status.FAILED, str(error) or type(error).__name__
    # Only the releases that were saved; one that failed is in the job's log.
    albums = importer.counts["albums"]
    result = WatchRun.objects.create(
        watch=watch,
        started_at=started,
        finished_at=timezone.now(),
        status=status,
        found=albums,
        detail=detail,
    )
    # ``update`` rather than ``save``, so edits made while the check ran are kept.
    Watch.objects.filter(pk=watch.pk).update(
        next_run_at=timezone.now() + timedelta(hours=watch.interval_hours)
    )
    log_activity(user, "watches.watch.checked", watch, {"status": status, "albums": albums})
    return result


def due_watches() -> list[Watch]:
    """Enabled watches whose next check is due."""
    return list(Watch.objects.filter(enabled=True, next_run_at__lte=timezone.now()))


def launch_due() -> None:
    """Start ``watch_check`` when a watch is due. Called by the scheduler.

    A check that is still running will pick up the due ones, so that is not an error.
    """
    if not Watch.objects.filter(enabled=True, next_run_at__lte=timezone.now()).exists():
        return
    try:
        runner.start("watch_check", {}, None)
    except runner.JobAlreadyRunning:
        pass
