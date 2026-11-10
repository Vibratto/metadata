"""Tests for startup and the scheduler."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from django.utils import timezone

from jobs import scheduler, startup
from jobs.models import JobRun


@pytest.fixture
def clean_scheduler(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Empty registry, thread stopped around."""
    monkeypatch.setattr(scheduler, "_periodics", {})
    yield
    scheduler.stop()


@pytest.mark.django_db
def test_mark_interrupted_closes_leftovers_only() -> None:
    left = [JobRun.objects.create(kind=f"k{status}", status=status) for status in JobRun.ACTIVE]
    done = JobRun.objects.create(
        kind="old", status=JobRun.Status.SUCCEEDED, finished_at=timezone.now()
    )
    assert startup.mark_interrupted() == 3
    for run in left:
        run.refresh_from_db()
        assert run.status == JobRun.Status.INTERRUPTED and run.is_closed
        assert run.lines.get().level == "warning"
    done.refresh_from_db()
    assert done.status == JobRun.Status.SUCCEEDED
    assert startup.mark_interrupted() == 0


@pytest.mark.django_db
def test_start_marks_interrupted_and_starts_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[bool] = []
    monkeypatch.setattr(scheduler, "start", lambda: started.append(True))
    JobRun.objects.create(kind="demo", status=JobRun.Status.RUNNING)
    startup.start()
    assert started == [True]
    assert JobRun.objects.get().status == JobRun.Status.INTERRUPTED


@pytest.mark.usefixtures("clean_scheduler")
def test_periodic_runs_when_due_and_then_waits_for_its_interval() -> None:
    calls: list[int] = []
    scheduler.register_periodic("demo", timedelta(hours=1), lambda: calls.append(1))
    now = timezone.now()
    scheduler.run_due(now)
    scheduler.run_due(now + timedelta(minutes=30))
    assert calls == [1]
    scheduler.run_due(now + timedelta(hours=1))
    assert calls == [1, 1]


@pytest.mark.django_db
@pytest.mark.usefixtures("clean_scheduler")
def test_failing_periodic_does_not_block_the_others(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[int] = []

    def boom() -> None:
        raise RuntimeError("x")

    scheduler.register_periodic("boom", timedelta(hours=1), boom)
    scheduler.register_periodic("ok", timedelta(hours=1), lambda: calls.append(1))
    scheduler.run_due()
    assert calls == [1]
    assert "Periodic function boom failed" in caplog.text


@pytest.mark.usefixtures("clean_scheduler")
def test_duplicate_periodic_name_is_rejected() -> None:
    scheduler.register_periodic("demo", timedelta(hours=1), lambda: None)
    with pytest.raises(ValueError, match="demo"):
        scheduler.register_periodic("demo", timedelta(hours=1), lambda: None)


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("clean_scheduler")
def test_thread_runs_due_functions_and_start_is_idempotent() -> None:
    import threading

    ran = threading.Event()
    scheduler.register_periodic("demo", timedelta(hours=1), ran.set)
    scheduler.start()
    first = scheduler._thread
    scheduler.start()
    assert scheduler._thread is first
    assert ran.wait(5)
    scheduler.stop()
    assert first is not None and not first.is_alive()


def test_stop_without_thread_is_harmless(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler, "_thread", None)
    scheduler.stop()
