"""Default preference values.

They live in code so that a setting never depends on a database row existing. Each
feature adds its keys here.
"""

from typing import Final

from integrations.audio import DEFAULT_TEMPLATE

DEFAULTS: Final[dict[str, object]] = {
    "download.format": "opus",
    "download.folder": "music",
    "download.name_template": DEFAULT_TEMPLATE,
    # The cover is stored once per album as cover.jpg; repeating it in every file only
    # takes up space.
    "tags.embed_cover": False,
    # Look up the lyrics after each download or upload.
    "lyrics.enabled": True,
    "replaygain.enabled": True,
    # Navidrome's separators; the first one joins the artists shown as a single text.
    "tags.artist_separators": [" / ", " feat. ", " feat ", " ft. ", " ft ", "; "],
    # A related artist is suggested for a full import once its monthly listeners (or
    # subscribers, when YouTube Music gives no listeners) reach this figure.
    "import.suggestion_threshold": 1_000_000,
}
