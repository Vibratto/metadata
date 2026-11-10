"""Catalogue fixtures: no catalogue test reaches a lyrics service."""

import pytest

from catalog.services import lyrics
from integrations import ytmusic as ytm
from integrations.lrclib import LrclibClient, Lyrics

#: The real factory, saved before the fixture below replaces it.
REAL_LYRICS_CLIENT = lyrics.lyrics_client


class FakeLrclib(LrclibClient):
    """Returns (or raises) a fixed answer and records what was asked."""

    def __init__(self) -> None:
        self.answer: Lyrics | None | Exception = None
        self.asked: list[tuple[str, str, str, int]] = []

    def get(self, title: str, artist: str, album: str, duration: int) -> Lyrics | None:
        self.asked.append((title, artist, album, duration))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class FakeYTLyrics:
    """The lyrics side of the YouTube Music client."""

    def __init__(self) -> None:
        self.answer: ytm.Lyrics | None | Exception = None
        self.asked: list[str] = []

    def get_lyrics(self, video_id: str) -> ytm.Lyrics | None:
        self.asked.append(video_id)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def lrclib() -> FakeLrclib:
    return FakeLrclib()


@pytest.fixture
def ytlyrics() -> FakeYTLyrics:
    return FakeYTLyrics()


@pytest.fixture(autouse=True)
def finder(
    monkeypatch: pytest.MonkeyPatch, lrclib: FakeLrclib, ytlyrics: FakeYTLyrics
) -> lyrics.LyricsFinder:
    """Finder over both fakes, installed wherever the application builds one."""
    fake = lyrics.LyricsFinder(lrclib, ytlyrics)
    monkeypatch.setattr(lyrics, "lyrics_client", lambda: fake)
    return fake
