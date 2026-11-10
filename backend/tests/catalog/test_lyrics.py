"""Lyrics lookup order and the ``.lrc`` file written next to the audio."""

import socket
from pathlib import Path
from typing import Any, cast

import pytest
import requests
import responses

from catalog.factories import (
    AlbumFactory,
    ArtistFactory,
    DownloadFactory,
    TrackArtistFactory,
    TrackFactory,
)
from catalog.models import Track
from catalog.services.lyrics import LyricsFinder, save_lyrics
from integrations import ytmusic as ytm
from integrations.lrclib import Lyrics
from integrations.lrclib.client import API_URL
from integrations.ytmusic import YTMusicError
from preferences.models import Preference
from proxies.models import Proxy

from .conftest import REAL_LYRICS_CLIENT, FakeLrclib, FakeYTLyrics

pytestmark = pytest.mark.django_db

SYNCED = "[00:01.00] One\n[00:02.00] Two\n"
PLAIN = "One\nTwo\n"
YT_SYNCED = ytm.Lyrics("[00:01.50]One\n[00:02.50]Two", synced=True)
YT_PLAIN = ytm.Lyrics("One (YT)\nTwo (YT)")


def _track(duration: int | None = 214, video_id: str | None = "vid-la-fama") -> Track:
    track = TrackFactory(
        title="La Fama",
        duration=duration,
        video_id=video_id,
        album=AlbumFactory(title="MOTOMAMI"),
        credit=None,
    )
    TrackArtistFactory(track=track, artist=ArtistFactory(name="Rosalía"), position=0)
    TrackArtistFactory(track=track, artist=ArtistFactory(name="The Weeknd"), position=1)
    return cast(Track, track)


def _audio(tmp_path: Path) -> Path:
    audio = tmp_path / "rosalia-1" / "motomami-2" / "01-02-la-fama-3.opus"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"audio")
    return audio


def test_asks_lrclib_with_the_catalogue_data(finder: LyricsFinder, lrclib: FakeLrclib) -> None:
    finder.find(_track())
    assert lrclib.asked == [("La Fama", "Rosalía, The Weeknd", "MOTOMAMI", 214)]


def test_synced_lrclib_lyrics_win_and_youtube_music_is_not_asked(
    finder: LyricsFinder, lrclib: FakeLrclib, ytlyrics: FakeYTLyrics
) -> None:
    lrclib.answer = Lyrics(synced=SYNCED, plain=PLAIN, instrumental=False)
    ytlyrics.answer = YT_SYNCED
    assert finder.find(_track()) == SYNCED
    assert ytlyrics.asked == []


@pytest.mark.parametrize("yt_answer", [YT_SYNCED, YT_PLAIN], ids=["timed", "plain"])
def test_youtube_music_lyrics_beat_plain_lrclib_lyrics(
    finder: LyricsFinder, lrclib: FakeLrclib, ytlyrics: FakeYTLyrics, yt_answer: ytm.Lyrics
) -> None:
    lrclib.answer = Lyrics(synced=None, plain=PLAIN, instrumental=False)
    ytlyrics.answer = yt_answer
    assert finder.find(_track()) == yt_answer.text
    assert ytlyrics.asked == ["vid-la-fama"]


def test_plain_lrclib_lyrics_when_youtube_music_has_none(
    finder: LyricsFinder, lrclib: FakeLrclib
) -> None:
    lrclib.answer = Lyrics(synced=None, plain=PLAIN, instrumental=False)
    assert finder.find(_track()) == PLAIN


def test_youtube_music_alone_is_enough(finder: LyricsFinder, ytlyrics: FakeYTLyrics) -> None:
    ytlyrics.answer = YT_PLAIN
    assert finder.find(_track()) == YT_PLAIN.text


def test_instrumental_tracks_are_not_looked_up_further(
    finder: LyricsFinder, lrclib: FakeLrclib, ytlyrics: FakeYTLyrics
) -> None:
    lrclib.answer = Lyrics(synced=None, plain=None, instrumental=True)
    ytlyrics.answer = YT_PLAIN
    assert finder.find(_track()) is None
    assert ytlyrics.asked == []


def test_track_without_duration_skips_lrclib_and_asks_youtube_music(
    finder: LyricsFinder, lrclib: FakeLrclib, ytlyrics: FakeYTLyrics
) -> None:
    lrclib.answer = Lyrics(synced=SYNCED, plain=None, instrumental=False)
    ytlyrics.answer = YT_PLAIN
    assert finder.find(_track(duration=None)) == YT_PLAIN.text
    assert lrclib.asked == []


def test_track_without_video_only_asks_lrclib(
    finder: LyricsFinder, lrclib: FakeLrclib, ytlyrics: FakeYTLyrics
) -> None:
    lrclib.answer = Lyrics(synced=None, plain=PLAIN, instrumental=False)
    assert finder.find(_track(video_id=None)) == PLAIN
    assert ytlyrics.asked == []


def test_nothing_anywhere_is_none(finder: LyricsFinder) -> None:
    assert finder.find(_track()) is None
    assert finder.find(_track(duration=None, video_id=None)) is None


def test_youtube_music_failure_falls_back_to_plain_lrclib_lyrics(
    finder: LyricsFinder, lrclib: FakeLrclib, ytlyrics: FakeYTLyrics
) -> None:
    lrclib.answer = Lyrics(synced=None, plain=PLAIN, instrumental=False)
    ytlyrics.answer = YTMusicError("down")
    assert finder.find(_track()) == PLAIN


def test_youtube_music_failure_without_fallback_is_raised(
    finder: LyricsFinder, ytlyrics: FakeYTLyrics
) -> None:
    ytlyrics.answer = YTMusicError("down")
    with pytest.raises(YTMusicError):
        finder.find(_track())


def test_lyrics_go_to_an_lrc_named_after_the_audio(
    tmp_path: Path, finder: LyricsFinder, lrclib: FakeLrclib
) -> None:
    audio = _audio(tmp_path)
    lrclib.answer = Lyrics(synced=SYNCED, plain=PLAIN, instrumental=False)
    assert save_lyrics(_track(), audio, finder) is True
    lrc = audio.with_suffix(".lrc")
    assert lrc.read_bytes() == SYNCED.encode("utf-8")
    assert sorted(p.name for p in audio.parent.iterdir()) == sorted([audio.name, lrc.name])


def test_file_is_utf8_without_bom_and_with_unix_newlines(
    tmp_path: Path, finder: LyricsFinder, lrclib: FakeLrclib
) -> None:
    audio = _audio(tmp_path)
    lrclib.answer = Lyrics(synced=None, plain="﻿Canción\r\nañil\r\n", instrumental=False)
    save_lyrics(_track(), audio, finder)
    assert audio.with_suffix(".lrc").read_bytes() == "Canción\nañil\n".encode()


def test_no_file_when_there_are_no_lyrics(tmp_path: Path, finder: LyricsFinder) -> None:
    audio = _audio(tmp_path)
    assert save_lyrics(_track(), audio, finder) is False
    assert list(audio.parent.iterdir()) == [audio]


def test_network_error_raises_and_leaves_no_file(
    tmp_path: Path, finder: LyricsFinder, lrclib: FakeLrclib
) -> None:
    audio = _audio(tmp_path)
    lrclib.answer = requests.ConnectionError("down")
    with pytest.raises(requests.ConnectionError):
        save_lyrics(_track(), audio, finder)
    assert list(audio.parent.iterdir()) == [audio]


def test_lyrics_of_the_same_recording_are_copied_not_looked_up_again(
    tmp_path: Path, finder: LyricsFinder, lrclib: FakeLrclib, ytlyrics: FakeYTLyrics
) -> None:
    Preference.objects.create(key="download.folder", value=str(tmp_path))
    single = _track()
    DownloadFactory(track=single, file_path="a/single/01-song-1.mp3")
    (tmp_path / "a" / "single").mkdir(parents=True)
    (tmp_path / "a" / "single" / "01-song-1.lrc").write_text(SYNCED)
    on_album = TrackFactory(recording=single.recording, credit=None)
    audio = _audio(tmp_path)

    assert save_lyrics(on_album, audio, finder) is True

    assert (lrclib.asked, ytlyrics.asked) == ([], [])
    assert audio.with_suffix(".lrc").read_text() == SYNCED


def test_sibling_without_lyrics_means_looking_them_up(
    tmp_path: Path, finder: LyricsFinder, lrclib: FakeLrclib
) -> None:
    Preference.objects.create(key="download.folder", value=str(tmp_path))
    single = _track()
    DownloadFactory(track=single, file_path="a/single/01-song-1.mp3")
    on_album = TrackFactory(recording=single.recording, credit=None)

    save_lyrics(on_album, _audio(tmp_path), finder)

    assert len(lrclib.asked) == 1


@responses.activate
def test_lrclib_is_reached_through_a_compatible_proxy(dns: Any) -> None:
    Proxy.objects.create(url="http://v4:3128")
    dns("lrclib.net", socket.AF_INET)
    responses.get(f"{API_URL}/get", status=404)

    assert REAL_LYRICS_CLIENT().find(_track(video_id=None)) is None
    assert Proxy.objects.get().success_count == 1
