"""LRCLIB client. The service is free and needs no key."""

from dataclasses import dataclass

import requests

from integrations.http import build_session
from integrations.ratelimit import RateLimiter

API_URL = "https://lrclib.net/api"
# LRCLIB asks for one request at a time, 200 to 500 ms apart.
MIN_INTERVAL = 0.3


@dataclass(frozen=True, slots=True)
class Lyrics:
    """A track's lyrics according to LRCLIB.

    Attributes:
        synced: Timed lyrics in LRC format, if any.
        plain: Untimed lyrics, if any.
        instrumental: The track has no lyrics at all.
    """

    synced: str | None
    plain: str | None
    instrumental: bool


class LrclibClient:
    def __init__(
        self, session: requests.Session | None = None, limiter: RateLimiter | None = None
    ) -> None:
        self._session = build_session() if session is None else session
        self._limiter = RateLimiter(MIN_INTERVAL) if limiter is None else limiter

    def get(self, title: str, artist: str, album: str, duration: int) -> Lyrics | None:
        """Look up a track's lyrics.

        Args:
            title: Track title.
            artist: Artist name.
            album: Album title.
            duration: Length in seconds; LRCLIB matches within ±2 s.

        Returns:
            The lyrics, or ``None`` if LRCLIB does not know the track.

        Raises:
            requests.RequestException: If the network or the service fails.
        """
        self._limiter.wait()
        response = self._session.get(
            f"{API_URL}/get",
            params={
                "track_name": title,
                "artist_name": artist,
                "album_name": album,
                "duration": str(duration),
            },
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        return Lyrics(
            synced=data.get("syncedLyrics") or None,
            plain=data.get("plainLyrics") or None,
            instrumental=bool(data.get("instrumental")),
        )
