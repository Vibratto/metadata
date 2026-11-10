"""``folder_import`` job: links music already on disk to the catalogue."""

from typing import Any

from django.utils.translation import gettext as _

from activity.services import log_activity
from catalog.services.folder_import import FolderImporter
from catalog.services.importing import ytmusic_client
from catalog.services.library import download_folder
from jobs import registry
from jobs.models import JobRun


@registry.register("folder_import")
def import_folder(run: JobRun, params: dict[str, Any]) -> dict[str, Any]:
    """Link the audio files under ``params["folder"]``.

    ``folder`` is relative to the library folder; empty or ``.`` means all of it.

    Returns:
        The counters, ``unlinked`` with every file left out and its reason, and
        ``completed``.

    Raises:
        ValueError: ``folder`` is not text, or it leaves the library folder.
    """
    folder = params.get("folder", "")
    if not isinstance(folder, str):
        raise ValueError(_("“folder” must be a path relative to the library folder."))
    importer = FolderImporter(run, ytmusic_client(), download_folder())
    completed = importer.import_folder(folder)
    summary: dict[str, Any] = {**importer.counts, "completed": completed}
    log_activity(
        run.user,
        "catalog.folder_import",
        detail={
            "folder": folder,
            "linked": importer.linked,
            "unlinked": len(importer.unlinked),
        },
    )
    return summary
