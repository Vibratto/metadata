"""New-release checks, their scheduling and the job that runs them."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from activity.models import ActivityLog
from catalog.factories import ArtistFactory
from catalog.models import Album, Artist, BlockedItem, Track
from integrations import ytmusic as ytm
from jobs import registry, runner, scheduler
from jobs.models import JobRun
from tests.catalog.test_importing import MAIN, FakeYTMusic
from watches import services
from watches.models import Watch, WatchArtist, WatchRun

pytestmark = pytest.mark.django_db


@pytest.fixture
def ytmusic(monkeypatch: pytest.MonkeyPatch) -> FakeYTMusic:
    """A fake YouTube Music, also used when the code builds its own client."""
    fake = FakeYTMusic()
    monkeypatch.setattr(services, "ytmusic_client", lambda: fake)
    return fake


@pytest.fixture
def run() -> JobRun:
    return JobRun.objects.create(kind="watch_check", status=JobRun.Status.RUNNING)


def _watch(*channel_ids: str | None, name: str = "w", **fields: Any) -> Watch:
    watch = Watch.objects.create(name=name, **fields)
    for position, channel_id in enumerate(channel_ids):
        artist = Artist.objects.filter(ytmusic_id=channel_id).first() if channel_id else None
        artist = artist or ArtistFactory(ytmusic_id=channel_id)
        WatchArtist.objects.create(watch=watch, artist=artist, position=position)
    return watch


@pytest.fixture
def downloads(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Register a ``download`` job that only records its params."""
    started: list[dict[str, Any]] = []
    monkeypatch.setitem(registry._tasks, "download", lambda run, params: started.append(params))
    return started


# --- check_watch ---


def test_check_imports_the_releases_the_catalogue_lacks(run: JobRun, ytmusic: FakeYTMusic) -> None:
    watch = _watch(MAIN)
    Album.objects.create(ytmusic_id="first", title="Already here")
    before = timezone.now()

    result = services.check_watch(watch, run, ytmusic)

    assert (result.status, result.found, result.detail) == ("succeeded", 1, "")
    assert set(Album.objects.values_list("ytmusic_id", flat=True)) == {"first", "second"}
    assert Album.objects.get(ytmusic_id="first").title == "Already here"
    assert ("album", "first") not in ytmusic.calls
    watch.refresh_from_db()
    assert watch.next_run_at >= before + timedelta(hours=24)
    entry = ActivityLog.objects.get(action="watches.watch.checked")
    assert entry.detail == {"status": "succeeded", "albums": 1}


def test_check_skips_blocked_releases_and_is_repeatable(run: JobRun, ytmusic: FakeYTMusic) -> None:
    watch = _watch(MAIN)
    BlockedItem.objects.create(kind="album", external_id="second")

    first = services.check_watch(watch, run, ytmusic)
    second = services.check_watch(watch, run, ytmusic)

    assert (first.found, second.found) == (1, 0)
    assert list(Album.objects.values_list("ytmusic_id", flat=True)) == ["first"]
    assert WatchRun.objects.filter(watch=watch).count() == 2


def test_check_does_not_import_the_related_artists(run: JobRun, ytmusic: FakeYTMusic) -> None:
    # A watch looks for new releases; only a full artist import saves related profiles.
    services.check_watch(_watch(MAIN), run, ytmusic)
    assert not Artist.objects.filter(ytmusic_id="UCrelated").exists()


def test_check_follows_the_order_of_the_watch_and_skips_artists_without_a_channel(
    run: JobRun, ytmusic: FakeYTMusic
) -> None:
    ytmusic.artists["UCsecond"] = ytm.Artist("UCsecond", "Second")
    ytmusic.releases["UCsecond"] = []
    services.check_watch(_watch("UCsecond", None, MAIN), run, ytmusic)
    asked = [key for kind, key in ytmusic.calls if kind == "artist"]
    assert asked == ["UCsecond", MAIN]


def test_release_that_fails_does_not_stop_the_check(
    run: JobRun, ytmusic: FakeYTMusic, noted_problems: Callable[[JobRun], list[dict[str, str]]]
) -> None:
    ytmusic.failing.add("first")
    result = services.check_watch(_watch(MAIN), run, ytmusic)
    assert (result.status, result.found) == ("succeeded", 1)
    assert noted_problems(run) == [
        {"item": "First", "reason": "YouTube Music did not answer as expected."}
    ]


def test_failed_check_is_recorded_and_rescheduled(run: JobRun, ytmusic: FakeYTMusic) -> None:
    watch = _watch(MAIN, interval_hours=2)
    ytmusic.failing.add(MAIN)
    before = timezone.now()

    result = services.check_watch(watch, run, ytmusic)

    assert (result.status, result.found) == ("failed", 0)
    assert result.detail == "YouTube Music did not answer as expected."
    watch.refresh_from_db()
    assert before + timedelta(hours=2) <= watch.next_run_at < before + timedelta(hours=3)
    assert ActivityLog.objects.get().detail == {"status": "failed", "albums": 0}


def test_an_unexpected_failure_is_recorded_without_its_technical_text(
    run: JobRun, ytmusic: FakeYTMusic, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(channel_id: str) -> ytm.ArtistPage:
        raise RuntimeError

    monkeypatch.setattr(ytmusic, "get_artist", boom)
    result = services.check_watch(_watch(MAIN), run, ytmusic)
    assert result.detail == "Something went wrong."


def test_edits_made_during_the_check_are_kept(
    run: JobRun, ytmusic: FakeYTMusic, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch = _watch(MAIN)
    real = ytmusic.get_artist

    def rename_meanwhile(channel_id: str) -> ytm.ArtistPage:
        Watch.objects.filter(pk=watch.pk).update(name="renamed")
        return real(channel_id)

    monkeypatch.setattr(ytmusic, "get_artist", rename_meanwhile)
    services.check_watch(watch, run, ytmusic)
    assert Watch.objects.get(pk=watch.pk).name == "renamed"


def test_client_is_built_when_none_is_given(run: JobRun, ytmusic: FakeYTMusic) -> None:
    assert services.check_watch(_watch(MAIN), run).found == 2


# --- Automatic download ---


def test_automatic_download_starts_with_the_new_tracks(
    run: JobRun, ytmusic: FakeYTMusic, downloads: list[dict[str, Any]]
) -> None:
    services.check_watch(_watch(MAIN, auto_download=True), run, ytmusic)
    assert downloads == [{"track_ids": sorted(Track.objects.values_list("pk", flat=True))}]


def test_no_download_without_the_option_or_without_news(
    run: JobRun, ytmusic: FakeYTMusic, downloads: list[dict[str, Any]]
) -> None:
    services.check_watch(_watch(MAIN, name="manual"), run, ytmusic)
    services.check_watch(_watch(name="auto", auto_download=True), run, ytmusic)
    assert downloads == []


def test_download_that_cannot_start_is_noted_without_failing_the_check(
    run: JobRun, ytmusic: FakeYTMusic, downloads: list[dict[str, Any]]
) -> None:
    JobRun.objects.create(kind="download", status=JobRun.Status.RUNNING)
    result = services.check_watch(_watch(MAIN, auto_download=True), run, ytmusic)
    assert (result.status, result.found) == ("succeeded", 2)
    assert result.detail == "The new tracks were not downloaded: another download is running."
    assert downloads == []


# --- Scheduling ---


def test_due_watches_are_the_enabled_ones_whose_time_has_come() -> None:
    due = Watch.objects.create(name="due")
    Watch.objects.create(name="off", enabled=False)
    Watch.objects.create(name="later", next_run_at=timezone.now() + timedelta(hours=1))
    assert services.due_watches() == [due]


def test_launch_due_starts_the_job_only_when_a_watch_is_due(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[str] = []
    monkeypatch.setattr(runner, "start", lambda kind, params, user: started.append(kind))

    Watch.objects.create(name="off", enabled=False)
    services.launch_due()
    assert started == []

    Watch.objects.create(name="due")
    services.launch_due()
    assert started == ["watch_check"]


def test_launch_due_tolerates_a_check_that_is_still_running(ytmusic: FakeYTMusic) -> None:
    Watch.objects.create(name="due")
    JobRun.objects.create(kind="watch_check", status=JobRun.Status.RUNNING)
    services.launch_due()
    assert JobRun.objects.filter(kind="watch_check").count() == 1


def test_job_and_periodic_check_are_registered() -> None:
    assert "watch_check" in registry.kinds()
    periodic = scheduler._periodics["watch_check"]
    assert periodic.func is services.launch_due
    assert periodic.interval == timedelta(minutes=5)


# --- Job ---


def test_job_checks_the_watches_that_are_due(ytmusic: FakeYTMusic) -> None:
    _watch(MAIN, name="due")
    _watch(MAIN, name="later", next_run_at=timezone.now() + timedelta(hours=1))

    run = runner.start("watch_check", {}, None)

    assert run.status == JobRun.Status.SUCCEEDED
    assert run.summary == {"checked": 1, "albums": 2, "failed": 0}
    assert (run.done, run.total) == (1, 1)


def test_job_checks_a_given_watch_even_when_it_is_disabled(ytmusic: FakeYTMusic) -> None:
    watch = _watch(MAIN, enabled=False, next_run_at=timezone.now() + timedelta(days=1))
    run = runner.start("watch_check", {"watch_id": watch.pk}, None)
    assert run.summary == {"checked": 1, "albums": 2, "failed": 0}


def test_job_reports_failed_checks(ytmusic: FakeYTMusic) -> None:
    _watch(MAIN, name="broken")
    ytmusic.failing.add(MAIN)
    run = runner.start("watch_check", {}, None)
    assert run.status == JobRun.Status.SUCCEEDED
    assert run.summary == {
        "checked": 1,
        "albums": 0,
        "failed": 1,
        "problems": [{"item": "broken", "reason": "YouTube Music did not answer as expected."}],
    }


def test_job_stops_between_watches(ytmusic: FakeYTMusic, monkeypatch: pytest.MonkeyPatch) -> None:
    _watch(name="a")
    _watch(name="b")
    answers = iter([False, True])
    monkeypatch.setattr(runner, "should_stop", lambda run: next(answers, True))
    run = runner.start("watch_check", {}, None)
    assert run.summary["checked"] == 1
