"""Tests for the task runner."""

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from accounts.models import Profile
from activity.logs import current_job_id
from core.errors import UserError
from jobs import registry, runner
from jobs.models import JobRun

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isolates the registry from real tasks."""
    monkeypatch.setattr(registry, "_tasks", {})
    yield


def test_successful_run_keeps_params_user_and_summary() -> None:
    user = User.objects.create_user("ana")
    seen: dict[str, Any] = {}

    @registry.register("demo")
    def task(run: JobRun, params: dict[str, Any]) -> dict[str, Any]:
        seen["params"], seen["job_id"] = params, current_job_id.get()
        runner.progress(run, 1, 2, "uno")
        return {"ok": 1}

    run = runner.start("demo", {"a": 1}, user)
    assert run.status == JobRun.Status.SUCCEEDED
    assert run.user == user and run.summary == {"ok": 1}
    assert (run.done, run.total, run.current) == (1, 2, "")
    assert run.is_closed
    assert seen == {"params": {"a": 1}, "job_id": str(run.pk)}
    assert current_job_id.get() == "-"


def test_task_returning_nothing_has_empty_summary() -> None:
    registry.register("demo")(lambda run, params: None)
    assert runner.start("demo", None, None).summary == {}


def test_failing_task_is_closed_as_failed_without_showing_the_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    @registry.register("demo")
    def task(run: JobRun, params: dict[str, Any]) -> None:
        raise RuntimeError("it broke")

    with caplog.at_level(logging.ERROR):
        run = runner.start("demo", None, None)
    assert run.status == JobRun.Status.FAILED and run.is_closed
    assert run.summary == {"error": "The task could not finish. Try again later."}
    assert "Job demo" in caplog.text and "it broke" in caplog.text


def test_an_error_the_user_can_fix_is_shown_as_it_is() -> None:
    @registry.register("demo")
    def task(run: JobRun, params: dict[str, Any]) -> None:
        raise UserError("Pick a folder.")

    run = runner.start("demo", None, None)
    assert run.status == JobRun.Status.FAILED
    assert run.summary == {"error": "Pick a folder."}


def test_problems_are_kept_in_the_summary() -> None:
    @registry.register("demo")
    def task(run: JobRun, params: dict[str, Any]) -> dict[str, Any]:
        runner.problem(run, "Song", "The connection failed.")
        return {"ok": 1}

    run = runner.start("demo", None, None)
    assert run.summary == {
        "ok": 1,
        "problems": [{"item": "Song", "reason": "The connection failed."}],
    }
    assert runner._problems == {}


def test_only_the_first_problems_are_kept_and_the_rest_counted() -> None:
    @registry.register("demo")
    def task(run: JobRun, params: dict[str, Any]) -> None:
        for number in range(runner.MAX_PROBLEMS + 3):
            runner.problem(run, f"Song {number}", "The connection failed.")

    summary = runner.start("demo", None, None).summary
    assert len(summary["problems"]) == runner.MAX_PROBLEMS
    assert summary["problems_omitted"] == 3


def test_problems_of_a_failed_run_are_kept_too() -> None:
    @registry.register("demo")
    def task(run: JobRun, params: dict[str, Any]) -> None:
        runner.problem(run, "Song", "The connection failed.")
        raise RuntimeError("it broke")

    summary = runner.start("demo", None, None).summary
    assert summary["problems"] == [{"item": "Song", "reason": "The connection failed."}]
    assert "error" in summary


def test_a_run_speaks_the_language_of_who_started_it() -> None:
    user = User.objects.create_user("ana")
    Profile.objects.create(user=user, language="es")

    @registry.register("demo")
    def task(run: JobRun, params: dict[str, Any]) -> None:
        raise RuntimeError("it broke")

    assert runner.start("demo", None, user).summary["error"].startswith("La tarea")
    assert runner.start("demo", None, None).summary["error"].startswith("La tarea")
    Profile.objects.all().delete()
    assert runner.start("demo", None, None).summary["error"].startswith("The task")


def test_unknown_kind_creates_nothing() -> None:
    with pytest.raises(registry.UnknownJobKind):
        runner.start("nope", None, None)
    assert not JobRun.objects.exists()


@pytest.mark.parametrize("status", JobRun.ACTIVE)
def test_only_one_run_per_kind(status: str) -> None:
    registry.register("demo")(lambda run, params: None)
    registry.register("other")(lambda run, params: None)
    JobRun.objects.create(kind="demo", status=status)
    with pytest.raises(runner.JobAlreadyRunning):
        runner.start("demo", None, None)
    assert runner.start("other", None, None).status == JobRun.Status.SUCCEEDED


def test_a_new_run_is_allowed_after_the_previous_one_closed() -> None:
    registry.register("demo")(lambda run, params: None)
    runner.start("demo", None, None)
    assert runner.start("demo", None, None).pk


def test_cooperative_stop() -> None:
    processed: list[int] = []

    @registry.register("demo")
    def task(run: JobRun, params: dict[str, Any]) -> dict[str, Any]:
        for item in range(5):
            if runner.should_stop(run):
                break
            processed.append(item)
            if item == 1:
                runner.stop(run.pk)
        return {"processed": len(processed)}

    run = runner.start("demo", None, None)
    assert processed == [0, 1]
    assert run.status == JobRun.Status.STOPPED
    assert run.is_closed and run.summary == {"processed": 2}


def test_stop_is_idempotent_while_stopping() -> None:
    run = JobRun.objects.create(kind="demo", status=JobRun.Status.RUNNING)
    assert runner.stop(run.pk).status == JobRun.Status.STOPPING
    assert runner.stop(run.pk).status == JobRun.Status.STOPPING


def test_stop_pending_run_closes_it_and_the_queue_skips_it() -> None:
    registry.register("demo")(lambda run, params: {"never": True})
    run = JobRun.objects.create(kind="demo")
    stopped = runner.stop(run.pk)
    assert stopped.status == JobRun.Status.STOPPED and stopped.is_closed
    runner._execute(run.pk)
    run.refresh_from_db()
    assert run.summary == {} and run.status == JobRun.Status.STOPPED


def test_executing_a_run_leaves_other_queued_runs_alone() -> None:
    """Each thread claims only its own run; the others stay queued."""
    registry.register("demo")(lambda run, params: None)
    registry.register("other")(lambda run, params: None)
    run = JobRun.objects.create(kind="demo")
    queued = JobRun.objects.create(kind="other")
    runner._execute(run.pk)
    queued.refresh_from_db()
    assert queued.status == JobRun.Status.PENDING


def test_stop_closed_run_raises() -> None:
    registry.register("demo")(lambda run, params: None)
    run = runner.start("demo", None, None)
    with pytest.raises(runner.JobClosed):
        runner.stop(run.pk)


def test_progress_truncates_current_item() -> None:
    run = JobRun.objects.create(kind="demo")
    runner.progress(run, 1, 1, "x" * 300)
    run.refresh_from_db()
    assert len(run.current) == 255


@pytest.mark.django_db(transaction=True)
@override_settings(JOBS_SYNCHRONOUS=False)
def test_runs_in_a_worker_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    monkeypatch.setattr(runner, "_pool", None)

    @registry.register("demo")
    def task(run: JobRun, params: dict[str, Any]) -> dict[str, Any]:
        return {"thread": threading.current_thread().name}

    run = runner.start("demo", None, None)
    # Joined without querying: in-memory SQLite cannot read while the thread writes.
    pool = runner._get_pool()
    assert runner._get_pool() is pool
    pool.shutdown(wait=True)
    run.refresh_from_db()
    assert run.status == JobRun.Status.SUCCEEDED
    assert run.summary["thread"].startswith("job")
