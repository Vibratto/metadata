"""``import`` job: brings YouTube Music artists into the catalogue."""

from typing import Any

from django.utils.translation import gettext as _

from activity.services import log_activity
from catalog.services.importing import Importer, ytmusic_client
from core.errors import UserError
from jobs import registry
from jobs.models import JobRun


@registry.register("import")
def import_artists(run: JobRun, params: dict[str, Any]) -> dict[str, Any]:
    """Import the discography of every artist in ``params["artist_ids"]``.

    Raises:
        UserError: If ``artist_ids`` is not a non-empty list of channel ids.
    """
    ids = params.get("artist_ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i for i in ids):
        raise UserError(_("artist_ids must be a list of YouTube Music channel ids."))
    importer = Importer(run, ytmusic_client())
    completed = importer.import_artists(ids)
    summary: dict[str, Any] = {**importer.counts, "completed": completed}
    log_activity(run.user, "catalog.import", detail={"artist_ids": ids, **summary})
    return summary
