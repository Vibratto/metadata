"""Rules for artist credits and "feat." mentions in titles."""

import re
from collections.abc import Iterable

from integrations.ytmusic.models import ArtistRef

# shortcut: only "feat./ft./featuring" inside brackets is recognised; "with X" and a bare
# "- feat. X" are left in the title. Extend when real data needs it.
_FEAT = re.compile(r"\s*[(\[]\s*(?:feat\.?|ft\.?|featuring)\s+([^)\]]+)[)\]]", re.IGNORECASE)
# A guest named "Earth, Wind & Fire" is split here; it survives only when YouTube Music
# also lists it as a credited artist.
_SPLIT = re.compile(r"\s*(?:,|&|\band\b)\s*", re.IGNORECASE)


def split_featured(title: str) -> tuple[str, tuple[str, ...]]:
    """Return the title without its "feat." part, and the guests it named."""
    guests: list[str] = []
    for match in _FEAT.finditer(title):
        guests.extend(name for name in _SPLIT.split(match.group(1).strip()) if name)
    return _FEAT.sub("", title).strip(), tuple(guests)


def merge_artists(*groups: Iterable[ArtistRef]) -> tuple[ArtistRef, ...]:
    """Merge credit lists in order, without duplicates.

    Names compare case-insensitively; a credit with an id replaces an earlier one without.
    """
    merged: dict[str, ArtistRef] = {}
    for ref in (ref for group in groups for ref in group):
        key = ref.name.casefold()
        if key not in merged or (merged[key].id is None and ref.id is not None):
            merged[key] = ref
    return tuple(merged.values())
