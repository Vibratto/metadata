"""Daily deletion of old technical logs.

The purge is a periodic job, not a task: it takes a few milliseconds and needs
no progress or stop handling. It stays auditable through ``log_activity``.
"""

from datetime import timedelta

from activity.services import log_activity, purge_technical_logs
from jobs.scheduler import register_periodic


def _purge_daily() -> None:
    """Deletes expired technical logs and logs it."""
    deleted = purge_technical_logs()
    log_activity(None, "activity.technical_logs.purged", detail={"deleted": deleted})


register_periodic("activity.purge_technical_logs", timedelta(days=1), _purge_daily)
