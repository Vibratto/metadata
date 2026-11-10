"""YouTube Music client built on ytmusicapi, without signing in.

ytmusicapi returns loosely shaped dictionaries that change whenever YouTube Music changes
its pages. Everything that touches those dictionaries lives in this module, so the rest of
the application only sees the dataclasses in :mod:`integrations.ytmusic.models`.
"""

import re
from collections.abc import Iterable, Mapping
from typing import Any

from integrations.ytmusic.models import (
    ALBUM,
    EP,
    SINGLE,
    Album,
    Artist,
    ArtistPage,
    ArtistRef,
    Lyrics,
    ReleaseRef,
    SongHit,
    Track,
)
from integrations.ytmusic.names import merge_artists, split_featured

#: Host the proxy router keys its counters on.
YTMUSIC_URL = "https://music.youtube.com"

_CHANNEL_ID = re.compile(r"UC[\w-]{22}")
_COUNT = re.compile(r"(\d+(?:[.,]\d+)*)\s*(?:([KMB])(?![\w-]))?", re.IGNORECASE)
_MULTIPLIERS = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
_THUMBNAIL_SIZE = re.compile(r"=w\d+-h\d+")
# Large enough for cover.jpg; Google's image host scales to whatever size the URL asks for.
_COVER_SIZE = "=w1200-h1200"
_KINDS = {"album": ALBUM, "single": SINGLE, "ep": EP}


class YTMusicError(Exception):
    """YouTube Music could not be reached or returned something unusable."""


def parse_channel_id(text: str) -> str | None:
    """Extract an artist channel id from an id or a YouTube Music URL.

    Returns ``None`` when the text holds no channel id, e.g. when it is an artist name.
    """
    match = _CHANNEL_ID.search(text)
    return match.group(0) if match else None


def parse_count(text: object) -> int | None:
    """Turn "12.4M monthly audience" or "1,234 views" into a number."""
    if isinstance(text, int):
        return text
    match = _COUNT.search(text) if isinstance(text, str) else None
    if match is None:
        return None
    digits, suffix = match.groups()
    if suffix is None:
        return int(re.sub(r"[.,]", "", digits))
    return round(float(digits.replace(",", ".")) * _MULTIPLIERS[suffix.upper()])


def _image_url(thumbnails: object) -> str | None:
    """Largest thumbnail, rewritten to cover size when the host allows it."""
    candidates = [t for t in thumbnails if t.get("url")] if isinstance(thumbnails, list) else []
    if not candidates:
        return None
    largest = max(candidates, key=lambda t: t.get("width") or 0)
    return _THUMBNAIL_SIZE.sub(_COVER_SIZE, str(largest["url"]))


def _year(value: object) -> int | None:
    return int(value) if isinstance(value, int | str) and str(value).isdigit() else None


def _artist_refs(raw: object) -> tuple[ArtistRef, ...]:
    people = raw if isinstance(raw, list) else []
    return merge_artists(ArtistRef(p["name"], p.get("id") or None) for p in people if p.get("name"))


def _kind(raw: Mapping[str, Any], default: str) -> str:
    return _KINDS.get(str(raw.get("type") or "").casefold(), default)


def _release_ref(raw: Mapping[str, Any], default_kind: str) -> ReleaseRef | None:
    if not raw.get("browseId") or not raw.get("title"):
        return None
    return ReleaseRef(
        id=raw["browseId"],
        title=raw["title"],
        kind=_kind(raw, default_kind),
        year=_year(raw.get("year")),
        cover_url=_image_url(raw.get("thumbnails")),
    )


def parse_artist(raw: Mapping[str, Any], channel_id: str) -> Artist:
    """Build an artist profile from a ``get_artist`` response."""
    return Artist(
        id=channel_id,
        name=raw["name"],
        image_url=_image_url(raw.get("thumbnails")),
        description=raw.get("description") or None,
        monthly_listeners=parse_count(raw.get("monthlyListeners")),
        subscribers=parse_count(raw.get("subscribers")),
    )


def parse_track(raw: Mapping[str, Any], album_artists: tuple[ArtistRef, ...]) -> Track:
    """Build a track from an entry of ``get_album()["tracks"]``.

    Guests announced in the title ("Song (feat. X)") become credited artists, and a track
    without credits of its own inherits the album's.
    """
    title, guests = split_featured(raw["title"])
    credited = _artist_refs(raw.get("artists")) or album_artists
    return Track(
        title=title,
        artists=merge_artists(credited, (ArtistRef(name) for name in guests)),
        video_id=raw.get("videoId") or None,
        position=raw.get("trackNumber"),
        duration=raw.get("duration_seconds"),
        explicit=bool(raw.get("isExplicit")),
    )


def parse_album(raw: Mapping[str, Any], browse_id: str) -> Album:
    """Build a release and its track list from a ``get_album`` response."""
    artists = _artist_refs(raw.get("artists"))
    return Album(
        id=browse_id,
        title=raw["title"],
        artists=artists,
        kind=_kind(raw, ALBUM),
        year=_year(raw.get("year")),
        cover_url=_image_url(raw.get("thumbnails")),
        explicit=bool(raw.get("isExplicit")),
        tracks=tuple(parse_track(t, artists) for t in raw.get("tracks") or () if t.get("title")),
    )


def _lrc_line(line: Any) -> str:
    """One LRC line from a ytmusicapi ``LyricLine`` (``start_time`` in milliseconds)."""
    minutes, milliseconds = divmod(int(line.start_time), 60_000)
    return f"[{minutes:02d}:{milliseconds / 1000:05.2f}]{line.text}"


def parse_lyrics(raw: Mapping[str, Any] | None) -> Lyrics | None:
    """Build lyrics from a ``get_lyrics`` response; ``None`` when there are none."""
    if not raw or not raw.get("lyrics"):
        return None
    source = raw.get("source") or None
    if raw.get("hasTimestamps"):
        return Lyrics("\n".join(_lrc_line(line) for line in raw["lyrics"]), True, source)
    return Lyrics(str(raw["lyrics"]), False, source)


class YTMusicClient:
    """Reads public YouTube Music data.

    Args:
        api: A ``ytmusicapi.YTMusic`` instance. Created on first use when omitted, so
            importing this module never touches the network.
        session: ``requests`` session ytmusicapi sends its requests through; this is how
            the application routes them through its proxies.
    """

    def __init__(self, api: Any = None, *, session: Any = None) -> None:
        self._api = api
        self._session = session

    @property
    def api(self) -> Any:
        """The underlying ytmusicapi object."""
        if self._api is None:
            from ytmusicapi import YTMusic

            self._api = YTMusic(requests_session=self._session)
        return self._api

    def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Call ytmusicapi and turn any failure into :class:`YTMusicError`.

        ytmusicapi raises a different exception for each way a page can be malformed
        (``KeyError``, ``IndexError``, ``YTMusicServerError``...), hence the broad catch.
        """
        try:
            return getattr(self.api, method)(*args, **kwargs)
        except Exception as error:
            raise YTMusicError(f"{method} failed: {error}") from error

    def search_artists(self, query: str, limit: int = 10) -> tuple[Artist, ...]:
        """Artists matching a name, best match first."""
        results = self._call("search", query, filter="artists", limit=limit)
        return tuple(
            Artist(
                id=r["browseId"],
                name=r["artist"],
                image_url=_image_url(r.get("thumbnails")),
                subscribers=parse_count(r.get("subscribers")),
            )
            for r in results
            if r.get("browseId") and r.get("artist")
        )

    def search_songs(self, query: str, limit: int = 10) -> tuple[SongHit, ...]:
        """Songs matching a free-text query, best match first."""
        hits = []
        for r in self._call("search", query, filter="songs", limit=limit):
            if not r.get("videoId") or not r.get("title"):
                continue
            album = r.get("album") or {}
            hits.append(
                SongHit(
                    video_id=r["videoId"],
                    title=r["title"],
                    artists=_artist_refs(r.get("artists")),
                    album_id=album.get("id") or None,
                    album_title=album.get("name") or None,
                    duration=r.get("duration_seconds"),
                )
            )
        return tuple(hits)

    def _artist(self, channel_id: str) -> tuple[Mapping[str, Any], Artist]:
        raw = self._call("get_artist", channel_id)
        try:
            return raw, parse_artist(raw, channel_id)
        except (KeyError, TypeError) as error:
            raise YTMusicError(f"Unexpected artist page for {channel_id}") from error

    def get_artist_profile(self, channel_id: str) -> Artist:
        """An artist's profile alone: one request, no discography."""
        return self._artist(channel_id)[1]

    def get_artist(self, channel_id: str) -> ArtistPage:
        """An artist's profile, full discography and related artists."""
        raw, artist = self._artist(channel_id)
        releases = [
            *self._releases(raw.get("albums"), ALBUM),
            *self._releases(raw.get("singles"), SINGLE),
        ]
        related = (raw.get("related") or {}).get("results") or ()
        return ArtistPage(
            artist=artist,
            releases=tuple({release.id: release for release in releases}.values()),
            related=tuple(
                ArtistRef(r["title"], r["browseId"])
                for r in related
                if r.get("title") and r.get("browseId")
            ),
        )

    def _releases(self, shelf: Mapping[str, Any] | None, kind: str) -> Iterable[ReleaseRef]:
        """Every release of one shelf ("Albums" or "Singles") of an artist page.

        The page shows the first few; ``browseId`` and ``params`` lead to the full list.
        """
        if not shelf:
            return ()
        items = shelf.get("results") or ()
        if shelf.get("browseId") and shelf.get("params"):
            items = self._call("get_artist_albums", shelf["browseId"], shelf["params"], limit=None)
        return tuple(ref for ref in (_release_ref(item, kind) for item in items) if ref)

    def get_album(self, browse_id: str) -> Album:
        """A release with its tracks."""
        raw = self._call("get_album", browse_id)
        try:
            return parse_album(raw, browse_id)
        except (KeyError, TypeError) as error:
            raise YTMusicError(f"Unexpected album page for {browse_id}") from error

    def get_lyrics(self, video_id: str) -> Lyrics | None:
        """Lyrics of a track, timed when YouTube Music has them; ``None`` when it has none."""
        lyrics_id = self._call("get_watch_playlist", video_id).get("lyrics")
        if not lyrics_id:
            return None
        return parse_lyrics(self._call("get_lyrics", lyrics_id, timestamps=True))
