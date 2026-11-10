"""Plain data returned by the YouTube Music integration."""

from dataclasses import dataclass

ALBUM = "album"
SINGLE = "single"
EP = "ep"


@dataclass(frozen=True)
class ArtistRef:
    """An artist as credited on a release, a track or a "related" shelf.

    ``id`` is ``None`` when YouTube Music credits a name without a channel.
    """

    name: str
    id: str | None = None


@dataclass(frozen=True)
class Artist:
    """An artist profile."""

    id: str
    name: str
    image_url: str | None = None
    description: str | None = None
    monthly_listeners: int | None = None
    subscribers: int | None = None

    @property
    def audience(self) -> int:
        """Best available size estimate: monthly listeners, else subscribers."""
        return self.monthly_listeners or self.subscribers or 0


@dataclass(frozen=True)
class ReleaseRef:
    """A release as listed on an artist page, before its tracks are fetched."""

    id: str
    title: str
    kind: str = ALBUM
    year: int | None = None
    cover_url: str | None = None


@dataclass(frozen=True)
class ArtistPage:
    """Everything an artist page offers: profile, discography, related artists."""

    artist: Artist
    releases: tuple[ReleaseRef, ...] = ()
    related: tuple[ArtistRef, ...] = ()


@dataclass(frozen=True)
class Track:
    """A track on a release. ``artists`` is ordered, main artist first."""

    title: str
    artists: tuple[ArtistRef, ...]
    video_id: str | None = None
    position: int | None = None
    duration: int | None = None
    explicit: bool = False


@dataclass(frozen=True)
class Album:
    """A release with its track list."""

    id: str
    title: str
    artists: tuple[ArtistRef, ...]
    kind: str = ALBUM
    year: int | None = None
    cover_url: str | None = None
    explicit: bool = False
    tracks: tuple[Track, ...] = ()


@dataclass(frozen=True)
class SongHit:
    """A song search result: enough to decide whether it is the song looked for."""

    video_id: str
    title: str
    artists: tuple[ArtistRef, ...]
    album_id: str | None = None
    album_title: str | None = None
    duration: int | None = None


@dataclass(frozen=True)
class Lyrics:
    """Lyrics of a track. ``text`` is LRC when ``synced``, plain text otherwise."""

    text: str
    synced: bool = False
    source: str | None = None
