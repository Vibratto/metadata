"""Task engine startup with the server."""

from django.utils import timezone

from jobs import scheduler
from jobs.models import JobRun


def mark_interrupted() -> int:
    """Closes as ``interrupted`` the runs a restart left half-done. Pending ones
    count too: their queue is gone, and they would block their kind forever.

    Returns:
        Number of runs marked.
    """
    leftovers = JobRun.objects.filter(status__in=JobRun.ACTIVE)
    count = 0
    for run in leftovers:
        run.status, run.finished_at = JobRun.Status.INTERRUPTED, timezone.now()
        run.save(update_fields=["status", "finished_at"])
        count += 1
    return count


def start() -> None:
    """Prepares the engine; called by the WSGI and ASGI entry points, never by
    tests, ``migrate`` or ``manage.py`` commands.

    shortcut: assumes a single server process; with several workers a restarting one
    would also interrupt the others' runs. Upgrade to a heartbeat column if that changes.
    """
    mark_interrupted()
    scheduler.start()
