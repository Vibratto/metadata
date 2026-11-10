"""Tests for ``watches`` models."""

import pytest
from django.db.models import ProtectedError
from django.utils import timezone

from catalog.factories import ArtistFactory
from core.models import AppendOnlyError
from watches.models import Watch, WatchArtist, WatchRun

pytestmark = pytest.mark.django_db


def _run(watch: Watch) -> WatchRun:
    """Creates a minimal run."""
    run = WatchRun(watch=watch, status=WatchRun.Status.SUCCEEDED)
    run.save()
    return run


def test_watch_name_is_unique() -> None:
    Watch.objects.create(name="novedades")
    with pytest.raises(Exception, match="UNIQUE|unique"):
        Watch.objects.create(name="novedades")


def test_watch_change_is_recorded_in_history() -> None:
    watch = Watch.objects.create(name="novedades")
    watch.enabled = False
    watch.save()
    assert watch.history.count() == 2


def test_run_is_inserted_and_readable() -> None:
    run = _run(Watch.objects.create(name="novedades"))
    run.refresh_from_db()
    assert run.status == WatchRun.Status.SUCCEEDED
    assert run.found == 0


def test_run_save_on_existing_row_is_rejected() -> None:
    run = _run(Watch.objects.create(name="novedades"))
    run.found = 3
    with pytest.raises(AppendOnlyError):
        run.save()


def test_run_delete_is_rejected() -> None:
    run = _run(Watch.objects.create(name="novedades"))
    with pytest.raises(AppendOnlyError):
        run.delete()


def test_watch_with_runs_cannot_be_deleted() -> None:
    watch = Watch.objects.create(name="novedades")
    _run(watch)
    with pytest.raises(ProtectedError):
        watch.delete()


def test_watch_str_is_its_name() -> None:
    assert str(Watch(name="novedades")) == "novedades"


def test_watch_artist_is_unique_per_watch() -> None:
    watch, artist = Watch.objects.create(name="novedades"), ArtistFactory.create()
    WatchArtist.objects.create(watch=watch, artist=artist)
    assert str(WatchArtist.objects.get()) == f"novedades / {artist}"
    with pytest.raises(Exception, match="UNIQUE|unique"):
        WatchArtist.objects.create(watch=watch, artist=artist)


def test_new_watch_is_due_and_checked_daily_by_default() -> None:
    watch = Watch.objects.create(name="novedades")
    assert (watch.interval_hours, watch.auto_download) == (24, False)
    assert watch.next_run_at <= timezone.now()
