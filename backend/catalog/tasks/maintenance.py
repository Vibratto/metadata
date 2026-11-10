"""``maintenance`` job: the catalogue utilities.

The operations to run come in ``params["operations"]``; without it, all of them except
relocating.
"""

from collections.abc import Callable
from typing import Any

from django.utils.translation import gettext as _

from catalog.services.maintenance import (
    CHECK_FILES,
    COMPLETE_ALBUMS,
    COMPLETE_ARTISTS,
    DEFAULT_OPERATIONS,
    LYRICS,
    OPERATIONS,
    RELOCATE,
    REPLAYGAIN,
    RETAG,
    TAG_WRITERS,
    check_download_files,
    complete_albums,
    complete_artists,
    fetch_missing_lyrics,
    relocate_downloads,
    replaygain_albums,
    retag_downloads,
)
from jobs import runner
from jobs.models import JobRun
from jobs.registry import register

_STEPS: dict[str, Callable[[JobRun], dict[str, Any]]] = {
    RETAG: retag_downloads,
    REPLAYGAIN: replaygain_albums,
    RELOCATE: relocate_downloads,
    CHECK_FILES: check_download_files,
    COMPLETE_ARTISTS: complete_artists,
    LYRICS: fetch_missing_lyrics,
    COMPLETE_ALBUMS: complete_albums,
}


@register("maintenance")
def maintenance(run: JobRun, params: dict[str, Any]) -> dict[str, Any]:
    """Run the requested operations, always in the same order.

    Raises:
        ValueError: ``operations`` is not a list of known operations, or it asks to
            rewrite tags and relocate in the same run.
    """
    operations = params.get("operations", list(DEFAULT_OPERATIONS))
    if not isinstance(operations, list) or not all(op in OPERATIONS for op in operations):
        raise ValueError(_("Unknown maintenance operation."))
    # A file that is retagged and moved within one Navidrome scan becomes a new track.
    if RELOCATE in operations and any(op in TAG_WRITERS for op in operations):
        raise ValueError(_("Tags cannot be rewritten and files relocated in the same run."))
    summary: dict[str, Any] = {}
    for name in OPERATIONS:
        if name in operations and not runner.should_stop(run):
            summary[name] = _STEPS[name](run)
    return summary
