"""Portable file and folder names.

Names are ASCII lowercase with dashes plus the catalogue id, so they behave the same
on every filesystem (case, Unicode normalisation, forbidden characters), never
collide, never come out empty and do not change when a name is corrected. Navidrome
never shows them: what users see comes from the tags.
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath

from .tags import Tags

DEFAULT_TEMPLATE = "{albumartist}/{album}/{disc}-{track}-{title}"
_NOT_ALNUM = re.compile(r"[^a-z0-9]+")
_MAX_TEXT = 60


@dataclass(frozen=True)
class PathIds:
    """Catalogue ids that make names unique.

    ``artist`` and ``album_artist`` are the first credited artist of the track and of
    the album; ``None`` when there is none.
    """

    track: int
    album: int
    artist: int | None
    album_artist: int | None


def _ascii(text: str) -> str:
    """ASCII lowercase, one ``-`` per other run."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return _NOT_ALNUM.sub("-", plain).strip("-")


def slug(text: str, ident: int) -> str:
    """Portable name of ``text`` with its id.

    Returns:
        Or just ``<id>`` if no text is left.
    """
    cut = _ascii(text)[:_MAX_TEXT].rstrip("-")
    return f"{cut}-{ident}" if cut else str(ident)


def _named(names: tuple[str, ...], ident: int | None) -> str:
    return slug(names[0], ident) if names and ident is not None else ""


def render_path(template: str, tags: Tags, ids: PathIds, extension: str) -> PurePosixPath:
    """Builds a file's relative path.

    Placeholders: ``{albumartist}``, ``{artist}``, ``{album}`` and ``{title}`` (each a
    :func:`slug` with its id), ``{disc}`` and ``{track}`` (two digits) and ``{year}``
    (four digits). Literal text is made portable too, so no segment can add or escape
    folders.

    Args:
        template: Template with ``/`` between folders.
        tags: Tags of the track.
        ids: Catalogue ids.
        extension: Extension without the dot.

    Returns:
        Relative path matching that pattern.

    Raises:
        KeyError: Unknown placeholder.
        ValueError: A segment comes out empty.
    """
    artist = _named(tags.artists, ids.artist)
    values = {
        "albumartist": _named(tags.album_artists, ids.album_artist) or artist,
        "artist": artist,
        "album": slug(tags.album or "", ids.album),
        "title": slug(tags.title, ids.track),
        "disc": f"{tags.disc_number:02d}" if tags.disc_number else "",
        "track": f"{tags.track_number:02d}" if tags.track_number else "",
        "year": f"{tags.year:04d}" if tags.year else "",
    }
    parts = [_ascii(part.format_map(values)) for part in template.split("/") if part]
    if not parts or not all(parts):
        raise ValueError(f"template gives an empty path segment: {template!r}")
    parts[-1] = f"{parts[-1]}.{extension}"
    return PurePosixPath(*parts)
