"""YouTube Music catalogue: artists, releases, tracks and lyrics."""

from integrations.ytmusic.client import (
    YTMusicClient,
    YTMusicError,
    parse_channel_id,
    parse_handle,
)
from integrations.ytmusic.models import (
    Album,
    Artist,
    ArtistPage,
    ArtistRef,
    Lyrics,
    ReleaseRef,
    SongHit,
    Track,
)

__all__ = [
    "Album",
    "Artist",
    "ArtistPage",
    "ArtistRef",
    "Lyrics",
    "ReleaseRef",
    "SongHit",
    "Track",
    "YTMusicClient",
    "YTMusicError",
    "parse_channel_id",
    "parse_handle",
]
