"""``library_restore`` job: imports an uploaded backup.

``params["file"]`` names the file the API left in the temporary folder. The job deletes
it when it finishes, whatever the outcome.
"""

from typing import Any

from django.utils.translation import gettext as _

from catalog.backup import parse_backup, restore, upload_path
from jobs import runner
from jobs.models import JobRun, JobRunLine
from jobs.registry import register


@register("library_restore")
def library_restore(run: JobRun, params: dict[str, Any]) -> dict[str, Any]:
    """Add to the library whatever the backup has and the library lacks.

    Raises:
        BackupError: The file is not a valid backup.
    """
    path = upload_path(params.get("file"))
    try:
        summary = restore(parse_backup(path.read_bytes()))
    finally:
        path.unlink(missing_ok=True)
    runner.progress(run, 1, 1)
    runner.line(
        run,
        JobRunLine.Level.INFO,
        _("%(created)d items added, %(skipped)d already existed.") % summary,
    )
    return summary
