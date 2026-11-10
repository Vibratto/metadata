"""LRCLIB client tests without network."""

from urllib.parse import parse_qs, urlsplit

import pytest
import requests
import responses

from integrations.http import USER_AGENT
from integrations.lrclib import LrclibClient, Lyrics
from integrations.lrclib.client import API_URL, MIN_INTERVAL
from integrations.ratelimit import RateLimiter

GET_URL = f"{API_URL}/get"


class _FakeClock:
    """Clock that advances when slept on."""

    def __init__(self) -> None:
        """Starts at 0."""
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        """Instante actual. / Current time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Records and advances."""
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def clock() -> _FakeClock:
    """Reloj simulado. / Fake clock."""
    return _FakeClock()


@pytest.fixture
def client(clock: _FakeClock) -> LrclibClient:
    """Client without real waits."""
    return LrclibClient(limiter=RateLimiter(MIN_INTERVAL, clock.clock, clock.sleep))


def _query() -> dict[str, list[str]]:
    url = responses.calls[-1].request.url
    assert url is not None
    return parse_qs(urlsplit(url).query)


@responses.activate
def test_asks_by_title_artist_album_and_duration(client: LrclibClient) -> None:
    responses.get(GET_URL, json={"syncedLyrics": None, "plainLyrics": "la", "instrumental": False})
    client.get("Canción", "Artista", "Álbum", 214)
    assert _query() == {
        "track_name": ["Canción"],
        "artist_name": ["Artista"],
        "album_name": ["Álbum"],
        "duration": ["214"],
    }
    assert responses.calls[-1].request.headers["User-Agent"] == USER_AGENT


@responses.activate
def test_returns_synced_plain_and_instrumental(client: LrclibClient) -> None:
    responses.get(
        GET_URL,
        json={"syncedLyrics": "[00:01.00] la", "plainLyrics": "la", "instrumental": False},
    )
    assert client.get("t", "a", "b", 1) == Lyrics(
        synced="[00:01.00] la", plain="la", instrumental=False
    )


@responses.activate
def test_instrumental(client: LrclibClient) -> None:
    responses.get(GET_URL, json={"syncedLyrics": None, "plainLyrics": None, "instrumental": True})
    assert client.get("t", "a", "b", 1) == Lyrics(synced=None, plain=None, instrumental=True)


@responses.activate
def test_not_found_is_none(client: LrclibClient) -> None:
    responses.get(GET_URL, status=404, json={"code": 404, "name": "TrackNotFound", "message": "x"})
    assert client.get("t", "a", "b", 1) is None


@responses.activate
def test_other_errors_raise(client: LrclibClient) -> None:
    responses.get(GET_URL, status=400)
    with pytest.raises(requests.HTTPError):
        client.get("t", "a", "b", 1)


@responses.activate
def test_requests_go_one_after_another_with_a_pause(
    client: LrclibClient, clock: _FakeClock
) -> None:
    responses.get(GET_URL, status=404)
    client.get("t", "a", "b", 1)
    client.get("t", "a", "b", 1)
    assert clock.slept == [MIN_INTERVAL]
    assert 0.2 <= MIN_INTERVAL <= 0.5
