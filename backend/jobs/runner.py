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
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from accounts.models import language_of
from activity.logs import current_job_id
from core.errors import UserError
from jobs import registry
from jobs.models import JobRun

logger = logging.getLogger(__name__)

_pool: ThreadPoolExecutor | None = None
# Serializes "check no run of this kind is active" and "create the run".
_start_lock = threading.Lock()
# What each active run could not do, kept in memory until the run closes.
_problems: dict[int, list[dict[str, str]]] = {}
#: Problems kept in a summary; the rest are only counted.
MAX_PROBLEMS = 50


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
    stopped_in_queue = runs.filter(status=JobRun.Status.PENDING).update(
        status=JobRun.Status.STOPPED, finished_at=now
    )
    if not stopped_in_queue and not runs.filter(status=JobRun.Status.RUNNING).update(
        status=JobRun.Status.STOPPING
    ):
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


def problem(run: JobRun, item: str, reason: str) -> None:
    """Notes something the run could not do, to show it when the run closes.

    Args:
        run: Current run.
        item: What it was working on (a track, an album, a file), as the user knows it.
        reason: One sentence for the user, already translated. Never an exception text.
    """
    _problems.setdefault(run.pk, []).append({"item": item[:255], "reason": reason})


def _take_problems(run_id: int) -> dict[str, Any]:
    """The noted problems as summary keys; nothing when there were none."""
    noted = _problems.pop(run_id, [])
    if not noted:
        return {}
    kept: dict[str, Any] = {"problems": noted[:MAX_PROBLEMS]}
    if len(noted) > MAX_PROBLEMS:
        kept["problems_omitted"] = len(noted) - MAX_PROBLEMS
    return kept


def _finish(run: JobRun, status: str, summary: dict[str, Any]) -> None:
    """Closes the run with its status and its summary, problems included."""
    summary = {**summary, **_take_problems(run.pk)}
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
        # A thread has no request to take the language from: what the run tells the user
        # is written in the language of whoever started it.
        with translation.override(language_of(run.user)):
            try:
                summary = registry.get(run.kind)(run, run.params) or {}
                outcome = JobRun.Status.SUCCEEDED
            except UserError as error:
                summary, outcome = {"error": str(error)}, JobRun.Status.FAILED
            except Exception:
                # A failing task must not kill the thread. The cause goes to the server
                # log; the user gets a sentence, not an exception text.
                logger.exception("Job %s #%s failed", run.kind, run_id)
                summary = {"error": _("The task could not finish. Try again later.")}
                outcome = JobRun.Status.FAILED
            # Re-read: ``stop`` changes the status from outside the thread.
            run.refresh_from_db(fields=["status"])
            if outcome == JobRun.Status.SUCCEEDED and run.status == JobRun.Status.STOPPING:
                outcome = JobRun.Status.STOPPED
            _finish(run, outcome, summary)
    finally:
        _problems.pop(run_id, None)
        current_job_id.reset(token)
