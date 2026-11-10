"""New-release check task."""

from datetime import timedelta
from typing import Any

from jobs import runner
from jobs.models import JobRun
from jobs.registry import register
from jobs.scheduler import register_periodic
from watches import services
from watches.models import Watch, WatchRun


@register("watch_check")
def watch_check(run: JobRun, params: dict[str, Any]) -> dict[str, Any]:
    """Checks one watch (``watch_id``) or, without it, every watch that is due. An explicit
    ``watch_id`` is checked even if disabled or not due, as "check now" asks for it.

    Returns:
        Summary with watches checked, new albums and failures.
    """
    watch_id = params.get("watch_id")
    watches = list(Watch.objects.filter(pk=watch_id)) if watch_id else services.due_watches()
    summary = {"checked": 0, "albums": 0, "failed": 0}
    for done, watch in enumerate(watches):
        if runner.should_stop(run):
            break
        runner.progress(run, done, len(watches), watch.name)
        result = services.check_watch(watch, run)
        failed = result.status == WatchRun.Status.FAILED
        if result.detail:
            runner.problem(run, watch.name, result.detail)
        summary["checked"] += 1
        summary["albums"] += result.found
        summary["failed"] += failed
    runner.progress(run, summary["checked"], len(watches))
    return summary


register_periodic("watch_check", timedelta(minutes=5), services.launch_due)
