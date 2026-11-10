"""Background task runner.

Tasks run in a ``ThreadPoolExecutor`` inside the server process; their state
lives in the database (``JobRun``), so the web can follow them and stop them.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone

from activity.logs import current_job_id, redact
from jobs import registry
from jobs.models import JobRun, JobRunLine

logger = logging.getLogger(__name__)

_pool: ThreadPoolExecutor | None = None
# Serializes "check no run of this kind is active" and "create the run".
_start_lock = threading.Lock()


class JobAlreadyRunning(Exception):
    """A run of that kind is already active."""


class JobClosed(Exception):
    """The run has ended and cannot change."""


def _get_pool() -> ThreadPoolExecutor:
    """Creates the pool on first use."""
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=settings.JOBS_MAX_WORKERS, thread_name_prefix="job")
    return _pool


def start(kind: str, params: dict[str, Any] | None, user: User | None) -> JobRun:
    """Starts a background task.

    Args:
        kind: Registered kind.
        params: JSON params for the task.
        user: Who starts it; ``None`` for the system.

    Returns:
        The created run, not finished yet (unless ``JOBS_SYNCHRONOUS`` is on).

    Raises:
        UnknownJobKind: If the kind is not registered.
        JobAlreadyRunning: If one of that kind is active.
    """
    registry.get(kind)
    with _start_lock:
        if JobRun.objects.filter(kind=kind, status__in=JobRun.ACTIVE).exists():
            raise JobAlreadyRunning(kind)
        run = JobRun.objects.create(kind=kind, params=params or {}, user=user)
    if settings.JOBS_SYNCHRONOUS:
        _execute(run.pk)
        run.refresh_from_db()
    else:
        # After the caller's transaction commits: the thread must be able to see the row.
        transaction.on_commit(lambda: _get_pool().submit(_thread_main, run.pk))
    return run


def stop(run_id: int) -> JobRun:
    """Asks a task to stop; the task decides where, through ``should_stop``. A run
    still waiting in the queue is closed straight away.

    Raises:
        JobClosed: If the run had already ended.
    """
    now = timezone.now()
    runs = JobRun.objects.filter(pk=run_id)
    # ``update`` rather than ``save``: atomic, and never overwrites the thread's progress.
    if runs.filter(status=JobRun.Status.PENDING).update(
        status=JobRun.Status.STOPPED, finished_at=now
    ):
        line(runs.get(), JobRunLine.Level.INFO, "Stopped before it started.")
    elif not runs.filter(status=JobRun.Status.RUNNING).update(status=JobRun.Status.STOPPING):
        run = runs.get()
        if run.is_closed:
            raise JobClosed(run_id)
    return runs.get()


def should_stop(run: JobRun) -> bool:
    """Whether a stop was requested; tasks poll it between items."""
    return JobRun.objects.filter(pk=run.pk, status=JobRun.Status.STOPPING).exists()


def progress(run: JobRun, done: int, total: int, current: str = "") -> None:
    """Updates the visible progress."""
    run.done, run.total, run.current = done, total, current[:255]
    run.save(update_fields=["done", "total", "current"])


def line(run: JobRun, level: str, message: str) -> JobRunLine:
    """Appends a line to the run's log."""
    last = JobRunLine.objects.filter(run=run).aggregate(last=Max("position"))["last"] or 0
    return JobRunLine.objects.create(
        run=run, position=last + 1, level=level, message=redact(message)
    )


def _finish(run: JobRun, status: str, summary: dict[str, Any]) -> None:
    """Closes the run with its status and summary."""
    run.status, run.summary, run.finished_at = status, summary, timezone.now()
    run.current = ""
    run.save(update_fields=["status", "summary", "finished_at", "current"])


def _thread_main(run_id: int) -> None:
    """Thread entry point: closes its database connection when done."""
    try:
        _execute(run_id)
    finally:
        connection.close()


def _execute(run_id: int) -> None:
    """Thread body: runs the task and records the outcome."""
    token = current_job_id.set(str(run_id))
    try:
        updated = JobRun.objects.filter(pk=run_id, status=JobRun.Status.PENDING).update(
            status=JobRun.Status.RUNNING
        )
        if not updated:  # stopped while queued
            return
        run = JobRun.objects.get(pk=run_id)
        try:
            summary = registry.get(run.kind)(run, run.params) or {}
            outcome = JobRun.Status.SUCCEEDED
        except Exception as error:
            # A failing task must not kill the thread: it is logged and closed as failed.
            logger.exception("Job %s #%s failed", run.kind, run_id)
            line(run, JobRunLine.Level.ERROR, str(error) or type(error).__name__)
            summary, outcome = {}, JobRun.Status.FAILED
        # Re-read: ``stop`` changes the status from outside the thread.
        run.refresh_from_db(fields=["status"])
        if outcome == JobRun.Status.SUCCEEDED and run.status == JobRun.Status.STOPPING:
            outcome = JobRun.Status.STOPPED
        _finish(run, outcome, summary)
    finally:
        current_job_id.reset(token)
