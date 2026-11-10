"""The video a track would be downloaded from."""

import socket
from typing import Any

import pytest
from rest_framework.test import APIClient

from catalog.factories import TrackFactory
from catalog.services import downloading
from integrations.youtube import NoProxyAvailable, VideoMatch, YoutubeError
from proxies.models import Proxy

pytestmark = pytest.mark.django_db


def _url(pk: int) -> str:
    return f"/api/v1/catalog/tracks/{pk}/video/"


@pytest.fixture
def searches(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str], float]]:
    """Record searches and answer each with a fixed match."""
    seen: list[tuple[str, list[str], float]] = []

    def find(title: str, artists: list[str], duration: float, *, proxy: str | None) -> VideoMatch:
        seen.append((title, artists, duration))
        return VideoMatch("abcdefghijk", "Song (Official)", duration)

    monkeypatch.setattr(downloading, "find_best_video", find)
    return seen


def test_track_from_youtube_music_answers_with_its_own_video(
    api: APIClient, searches: list[tuple[str, list[str], float]]
) -> None:
    track = TrackFactory(video_id="vvvvvvvvvvv")
    response = api.get(_url(track.pk))
    assert response.status_code == 200
    assert response.json() == {
        "video_id": "vvvvvvvvvvv",
        "embed_url": "https://www.youtube-nocookie.com/embed/vvvvvvvvvvv",
    }
    assert searches == []


def test_track_without_a_video_is_searched_for(
    api: APIClient, searches: list[tuple[str, list[str], float]]
) -> None:
    track = TrackFactory(title="Song", video_id=None, duration=200)
    response = api.get(_url(track.pk))
    assert response.json()["video_id"] == "abcdefghijk"
    assert searches == [("Song", [track.credits.get().artist.name], 200.0)]


@pytest.mark.parametrize("duration", [None, 200], ids=["no-duration", "no-match"])
def test_404_when_there_is_nothing_to_preview(
    api: APIClient, monkeypatch: pytest.MonkeyPatch, duration: int | None
) -> None:
    monkeypatch.setattr(downloading, "find_best_video", lambda *a, **k: None)
    track = TrackFactory(video_id=None, duration=duration)
    response = api.get(_url(track.pk))
    assert response.status_code == 404
    assert response.json() == {"detail": "No video matches the track."}


@pytest.mark.parametrize(
    ("error", "code"), [(YoutubeError("boom"), 502), (NoProxyAvailable(30), 503)]
)
def test_search_failures(
    api: APIClient, monkeypatch: pytest.MonkeyPatch, error: Exception, code: int
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(downloading, "find_best_video", fail)
    assert api.get(_url(TrackFactory(video_id=None, duration=200).pk)).status_code == code


def test_search_does_not_go_out_directly_when_no_proxy_is_compatible(
    api: APIClient, monkeypatch: pytest.MonkeyPatch, dns: Any
) -> None:
    Proxy.objects.create(url="http://v6:3128", ip_version=Proxy.IpVersion.IPV6)
    dns("www.youtube.com", socket.AF_INET)
    searched: list[object] = []
    monkeypatch.setattr(downloading, "find_best_video", lambda *a, **k: searched.append(a))
    response = api.get(_url(TrackFactory(video_id=None, duration=200).pk))
    assert response.status_code == 503
    assert response.json() == {
        "detail": "No enabled proxy supports the IP version of www.youtube.com."
    }
    assert searched == []


def test_unknown_track_is_a_404(api: APIClient) -> None:
    assert api.get(_url(99999)).status_code == 404


def test_a_session_is_required(anonymous: APIClient) -> None:
    assert anonymous.get(_url(TrackFactory().pk)).status_code == 403
