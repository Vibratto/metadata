"""Tests for the task runner."""

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from activity.logs import current_job_id
from jobs import registry, runner
from jobs.models import JobRun, JobRunLine

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
        runner.line(run, JobRunLine.Level.INFO, "hecho")
        return {"ok": 1}

    run = runner.start("demo", {"a": 1}, user)
    assert run.status == JobRun.Status.SUCCEEDED
    assert run.user == user and run.summary == {"ok": 1}
    assert (run.done, run.total, run.current) == (1, 2, "")
    assert run.is_closed
    assert seen == {"params": {"a": 1}, "job_id": str(run.pk)}
    assert current_job_id.get() == "-"
    assert list(run.lines.values_list("position", "message")) == [(1, "hecho")]


def test_task_returning_nothing_has_empty_summary() -> None:
    registry.register("demo")(lambda run, params: None)
    assert runner.start("demo", None, None).summary == {}


def test_failing_task_is_closed_as_failed_with_an_error_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    @registry.register("demo")
    def task(run: JobRun, params: dict[str, Any]) -> None:
        raise RuntimeError("it broke")

    with caplog.at_level(logging.ERROR):
        run = runner.start("demo", None, None)
    assert run.status == JobRun.Status.FAILED and run.is_closed
    line = run.lines.get()
    assert (line.level, line.message) == (JobRunLine.Level.ERROR, "it broke")
    assert "Job demo" in caplog.text


def test_failing_task_without_message_uses_exception_name() -> None:
    def task(run: JobRun, params: dict[str, Any]) -> None:
        raise ValueError

    registry.register("demo")(task)
    assert runner.start("demo", None, None).lines.get().message == "ValueError"


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
    assert stopped.lines.get().message == "Stopped before it started."
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


def test_line_positions_increase() -> None:
    run = JobRun.objects.create(kind="demo")
    for text in "abc":
        runner.line(run, JobRunLine.Level.INFO, text)
    assert list(run.lines.values_list("position", flat=True)) == [1, 2, 3]


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


def test_job_lines_hide_secrets() -> None:
    """Run lines are shown in the web interface, so they must never carry credentials."""
    run = JobRun.objects.create(kind="demo")

    saved = runner.line(run, JobRunLine.Level.ERROR, "fallo con http://bob:s3cr3t@h:1 token=abc")

    assert "s3cr3t" not in saved.message
    assert "abc" not in saved.message
