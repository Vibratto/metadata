"""Download task tests."""

import socket
import time
from pathlib import Path
from typing import Any

import pytest
import requests

from activity.models import ActivityLog
from catalog.factories import AlbumFactory, DownloadFactory, TrackFactory
from catalog.models import Download, DownloadLoudness, Track
from catalog.services import downloading, library, replaygain
from integrations.audio import Loudness
from integrations.lrclib import Lyrics
from integrations.youtube import NoProxyAvailable, VideoMatch, YoutubeError
from jobs import runner
from jobs.models import JobRun
from preferences.models import Preference
from proxies.models import Proxy

from .conftest import FakeLrclib

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fake_media(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Replaces yt-dlp, ffmpeg and mutagen; returns what they were asked."""
    calls: dict[str, Any] = {
        "proxies": [], "tagged": [], "searched": [], "fetched": [], "measured": [], "albums": []
    }  # fmt: skip
    Preference.objects.create(key="download.folder", value=str(tmp_path / "library"))

    def find(title: str, artists: list[str], duration: float, *, proxy: str | None) -> VideoMatch:
        calls["searched"].append((title, artists, duration))
        return VideoMatch("abcdefghijk", title, duration)

    def fetch(video_id: str, dest_dir: Path, *, proxy: str | None) -> Path:
        calls["proxies"].append(proxy)
        calls["fetched"].append((video_id, proxy))
        raw = dest_dir / "audio.webm"
        raw.write_bytes(b"raw")
        return raw

    def to_format(source: Path, dest_dir: Path, fmt: str) -> Path:
        out = dest_dir / f"{source.stem}.{fmt}"
        out.write_bytes(b"audio")
        return out

    monkeypatch.setattr(downloading, "find_best_video", find)
    monkeypatch.setattr(downloading, "download_audio", fetch)
    monkeypatch.setattr(downloading, "convert", to_format)
    monkeypatch.setattr(
        library, "write_tags", lambda path, tags: calls["tagged"].append((path.name, tags))
    )

    def loudness(paths: list[Path]) -> Loudness:
        calls["measured"].append([path.name for path in paths])
        return Loudness(lufs=-14.0, peak=0.9)

    def update_album(album: Any) -> int:
        calls["albums"].append(album.pk)
        return 1

    monkeypatch.setattr(replaygain, "measure_loudness", loudness)
    monkeypatch.setattr(replaygain, "update_album", update_album)
    return calls


def _run(**params: Any) -> JobRun:
    return runner.start("download", params, None)


def test_downloads_converts_tags_and_records(fake_media: dict[str, Any], tmp_path: Path) -> None:
    track = TrackFactory(title="Song", duration=200, video_id="vvvvvvvvvvv")
    run = _run(track_ids=[track.pk])

    assert run.status == JobRun.Status.SUCCEEDED
    assert run.summary == {"downloaded": 1, "failed": 0, "skipped": 0}
    download = Download.objects.get(track=track)
    # Relative, portable, with the id.
    assert download.file_path.endswith(f"-song-{track.pk}.opus")
    assert not Path(download.file_path).is_absolute()
    assert (tmp_path / "library" / download.file_path).read_bytes() == b"audio"
    assert download.audio_format == "opus"
    assert download.source_url == "https://music.youtube.com/watch?v=vvvvvvvvvvv"
    assert fake_media["tagged"][0][0] == "audio.opus"
    assert fake_media["tagged"][0][1].title == "Song"
    # The track carries its video id, so nothing is searched.
    assert fake_media["fetched"] == [("vvvvvvvvvvv", None)]
    assert fake_media["searched"] == []
    assert ActivityLog.objects.filter(action="catalog.download.finished").exists()


def test_track_without_a_video_is_searched_for(fake_media: dict[str, Any]) -> None:
    track = TrackFactory(title="Song", duration=200, video_id=None)
    _run(track_ids=[track.pk])
    assert fake_media["searched"] == [("Song", list(fake_media["tagged"][0][1].artists), 200.0)]
    assert fake_media["fetched"] == [("abcdefghijk", None)]
    assert Download.objects.get().source_url.endswith("watch?v=abcdefghijk")


def test_respects_format_preference(tmp_path: Path) -> None:
    Preference.objects.create(key="download.format", value="flac")
    track = TrackFactory(duration=200)
    _run(track_ids=[track.pk])
    assert Download.objects.get(track=track).audio_format == "flac"


def test_already_downloaded_track_is_not_repeated(fake_media: dict[str, Any]) -> None:
    done = DownloadFactory(track=TrackFactory(duration=200)).track
    run = _run(track_ids=[done.pk])
    assert run.summary == {"downloaded": 0, "failed": 0, "skipped": 1}
    assert Download.objects.filter(track=done).count() == 1
    assert fake_media["proxies"] == []


def test_all_pending_skips_downloaded() -> None:
    DownloadFactory(track=TrackFactory(duration=200))
    pending = TrackFactory(duration=200)
    run = _run(all_pending=True)
    assert run.summary["downloaded"] == 1
    assert Download.objects.filter(track=pending).exists()


def test_failure_of_one_track_does_not_stop_the_rest() -> None:
    broken = TrackFactory(title="Broken", duration=None, video_id=None)
    fine = TrackFactory(title="Fine", duration=200)
    run = _run(track_ids=[broken.pk, fine.pk])
    assert run.status == JobRun.Status.SUCCEEDED
    assert run.summary == {"downloaded": 1, "failed": 1, "skipped": 0}
    assert run.lines.filter(level="error", message__contains="Broken").exists()


def test_track_without_matching_video_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(downloading, "find_best_video", lambda *a, **k: None)
    run = _run(track_ids=[TrackFactory(duration=200, video_id=None).pk])
    assert run.summary["failed"] == 1
    assert Download.objects.count() == 0


def test_proxy_counters_on_success_and_failure(
    fake_media: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    Proxy.objects.create(url="http://proxy:3128")
    Proxy.objects.create(url="http://off:3128", enabled=False)
    ok = TrackFactory(duration=200)
    _run(track_ids=[ok.pk])
    proxy = Proxy.objects.get(url="http://proxy:3128")
    assert (proxy.success_count, proxy.failure_count) == (1, 0)
    assert proxy.last_used_at is not None
    assert fake_media["proxies"] == ["http://proxy:3128"]
    assert fake_media["fetched"] == [(ok.video_id, "http://proxy:3128")]

    def boom(*args: Any, **kwargs: Any) -> Path:
        raise YoutubeError("blocked")

    monkeypatch.setattr(downloading, "download_audio", boom)
    _run(track_ids=[TrackFactory(duration=200).pk])
    proxy.refresh_from_db()
    assert (proxy.success_count, proxy.failure_count) == (1, 1)
    assert proxy.last_failed_at is not None
    assert Proxy.objects.get(url="http://off:3128").success_count == 0


def test_all_proxies_cooling_down_fails_tracks() -> None:
    Proxy.objects.create(url="http://proxy:3128")
    pool = downloading.build_pool()
    pool.report_failure("http://proxy:3128", 10**12)
    track = TrackFactory(duration=200)
    with pytest.raises(NoProxyAvailable):
        downloading.download_track(track, pool, fmt="mp3", folder=Path("x"), template="{title}")


def test_waits_for_a_proxy_and_retries_the_same_track(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no proxy free the job waits as the pool asks; the track is not counted as failed."""
    from catalog.tasks import downloading as task

    real = downloading.download_track
    attempts: list[int] = []
    slept: list[float] = []

    def busy_once(track: Track, *args: Any, **kwargs: Any) -> Download:
        attempts.append(track.pk)
        if len(attempts) == 1:
            raise NoProxyAvailable(3)
        return real(track, *args, **kwargs)

    monkeypatch.setattr(task, "download_track", busy_once)
    monkeypatch.setattr(task.time, "sleep", slept.append)
    track = TrackFactory(duration=200)
    run = _run(track_ids=[track.pk])
    assert run.summary == {"downloaded": 1, "failed": 0, "skipped": 0}
    assert attempts == [track.pk, track.pk]
    assert sum(slept) >= 3


def test_stop_while_waiting_for_a_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stop requested during the wait is honoured without sitting it out."""
    from catalog.tasks import downloading as task

    def always_busy(*args: Any, **kwargs: Any) -> Download:
        raise NoProxyAvailable(3600)

    def sleep(seconds: float) -> None:
        JobRun.objects.update(status=JobRun.Status.STOPPING)

    monkeypatch.setattr(task, "download_track", always_busy)
    monkeypatch.setattr(task.time, "sleep", sleep)
    run = _run(track_ids=[TrackFactory(duration=200).pk])
    assert run.status == JobRun.Status.STOPPED
    assert run.summary == {"downloaded": 0, "failed": 0, "skipped": 0}


def test_stop_is_cooperative_between_tracks(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = TrackFactory(duration=200), TrackFactory(duration=200)
    real = downloading.download_track

    def stop_after_first(track: Track, *args: Any, **kwargs: Any) -> Download:
        result = real(track, *args, **kwargs)
        JobRun.objects.update(status=JobRun.Status.STOPPING)
        return result

    from catalog.tasks import downloading as task

    monkeypatch.setattr(task, "download_track", stop_after_first)
    run = _run(track_ids=[first.pk, second.pk])
    assert run.status == JobRun.Status.STOPPED
    assert Download.objects.count() == 1


def test_requires_track_ids_or_all_pending() -> None:
    run = _run()
    assert run.status == JobRun.Status.FAILED


def test_unsupported_format_fails_the_run() -> None:
    Preference.objects.create(key="download.format", value="wav")
    run = _run(all_pending=True)
    assert run.status == JobRun.Status.FAILED


def test_youtube_failure_without_proxies_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: Any, **kwargs: Any) -> Path:
        raise YoutubeError("blocked")

    monkeypatch.setattr(downloading, "download_audio", boom)
    run = _run(track_ids=[TrackFactory(duration=200).pk])
    assert run.summary["failed"] == 1


def test_youtube_failure_cools_the_proxy_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """After a network failure the same proxy is not reused straight away."""
    Proxy.objects.create(url="http://proxy:3128")
    pool = downloading.build_pool()

    def boom(*args: Any, **kwargs: Any) -> Path:
        raise YoutubeError("blocked")

    monkeypatch.setattr(downloading, "download_audio", boom)
    track = TrackFactory(duration=200)
    with pytest.raises(YoutubeError):
        downloading.download_track(track, pool, fmt="mp3", folder=Path("x"), template="{title}")
    with pytest.raises(NoProxyAvailable):
        pool.acquire(time.monotonic())


def test_youtube_only_uses_proxies_it_can_reach(fake_media: dict[str, Any], dns: Any) -> None:
    Proxy.objects.create(url="http://v6:3128", ip_version=Proxy.IpVersion.IPV6)
    Proxy.objects.create(url="http://v4:3128", ip_version=Proxy.IpVersion.IPV4)
    dns("www.youtube.com", socket.AF_INET)
    _run(track_ids=[TrackFactory(duration=200).pk, TrackFactory(duration=200).pk])
    assert set(fake_media["proxies"]) == {"http://v4:3128"}


def test_measures_each_track_and_updates_each_album_once(fake_media: dict[str, Any]) -> None:
    first = TrackFactory(duration=200)
    second = TrackFactory(album=first.album, duration=200)
    other = TrackFactory(duration=200)

    run = _run(track_ids=[first.pk, second.pk, other.pk])

    assert run.summary == {"downloaded": 3, "failed": 0, "skipped": 0}
    assert fake_media["measured"] == [["audio.opus"]] * 3
    assert {row.lufs for row in DownloadLoudness.objects.all()} == {-14.0}
    assert DownloadLoudness.objects.count() == 3
    assert fake_media["tagged"][0][1].replaygain.track_gain_db == -4.0
    assert sorted(fake_media["albums"]) == sorted([first.album.pk, other.album.pk])


def test_album_gain_failure_is_reported_without_failing_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(album: Any) -> int:
        raise OSError("disco lleno")

    monkeypatch.setattr(replaygain, "update_album", broken)
    track = TrackFactory(duration=200)

    run = _run(track_ids=[track.pk])

    assert run.status == JobRun.Status.SUCCEEDED
    assert run.summary == {"downloaded": 1, "failed": 0, "skipped": 0}
    assert any("disco lleno" in line for line in run.lines.values_list("message", flat=True))


def test_replaygain_off_measures_nothing(fake_media: dict[str, Any]) -> None:
    Preference.objects.create(key="replaygain.enabled", value=False)
    track = TrackFactory(duration=200)

    _run(track_ids=[track.pk])

    assert fake_media["measured"] == []
    assert fake_media["albums"] == []
    assert fake_media["tagged"][0][1].replaygain is None
    assert not DownloadLoudness.objects.exists()


def test_saves_the_lyrics_next_to_the_downloaded_audio(lrclib: FakeLrclib, tmp_path: Path) -> None:
    lrclib.answer = Lyrics(synced="[00:01.00] Hola\n", plain="Hola\n", instrumental=False)
    track = TrackFactory(title="Song", duration=200)

    _run(track_ids=[track.pk])

    audio = tmp_path / "library" / Download.objects.get(track=track).file_path
    assert audio.with_suffix(".lrc").read_text(encoding="utf-8") == "[00:01.00] Hola\n"


def test_lyrics_failure_is_logged_and_the_download_still_succeeds(lrclib: FakeLrclib) -> None:
    lrclib.answer = requests.ConnectionError("LRCLIB is down")
    track = TrackFactory(title="Song", duration=200)

    run = _run(track_ids=[track.pk])

    assert run.status == JobRun.Status.SUCCEEDED
    assert run.summary == {"downloaded": 1, "failed": 0, "skipped": 0}
    assert Download.objects.filter(track=track).exists()
    assert any("LRCLIB is down" in m for m in run.lines.values_list("message", flat=True))


def test_lyrics_are_not_looked_up_when_turned_off(lrclib: FakeLrclib) -> None:
    Preference.objects.create(key="lyrics.enabled", value=False)
    _run(track_ids=[TrackFactory(duration=200).pk])
    assert lrclib.asked == []


# --- One recording on several albums ---


def _downloaded_on_a_single(fake_media: dict[str, Any]) -> tuple[Any, Any]:
    """The single, already downloaded, and the album track that repeats its recording."""
    single = TrackFactory(title="Song", duration=200, album=AlbumFactory(title="Single"))
    _run(track_ids=[single.pk])
    fake_media["fetched"].clear()
    fake_media["searched"].clear()
    fake_media["tagged"].clear()
    fake_media["measured"].clear()
    on_album = TrackFactory(
        title="Song", album=AlbumFactory(title="Album"), recording=single.recording, credit=None
    )
    return single, on_album


def test_track_of_a_known_recording_copies_the_audio_without_youtube(
    fake_media: dict[str, Any], tmp_path: Path
) -> None:
    single, on_album = _downloaded_on_a_single(fake_media)

    run = _run(track_ids=[on_album.pk])

    assert run.summary == {"downloaded": 1, "failed": 0, "skipped": 0}
    assert fake_media["fetched"] == [] and fake_media["searched"] == []
    first, copy = Download.objects.get(track=single), Download.objects.get(track=on_album)
    assert copy.file_path != first.file_path
    assert (tmp_path / "library" / copy.file_path).read_bytes() == b"audio"
    assert (copy.audio_format, copy.source_url) == (first.audio_format, first.source_url)
    # It carries its own album's tags.
    assert fake_media["tagged"][-1][1].album == "Album"
    assert (tmp_path / "library" / first.file_path).exists()  # el original no se toca


def test_copy_reuses_the_measured_loudness(fake_media: dict[str, Any]) -> None:
    single, on_album = _downloaded_on_a_single(fake_media)

    _run(track_ids=[on_album.pk])

    copy = Download.objects.get(track=on_album)
    assert fake_media["measured"] == []
    original = DownloadLoudness.objects.get(download__track=single)
    assert (copy.loudness.lufs, copy.loudness.peak) == (original.lufs, original.peak)


def test_copy_does_not_need_a_duration(fake_media: dict[str, Any]) -> None:
    _, on_album = _downloaded_on_a_single(fake_media)
    on_album.recording.duration = None
    on_album.recording.save()

    assert _run(track_ids=[on_album.pk]).summary["downloaded"] == 1


def test_missing_source_file_falls_back_to_youtube(
    fake_media: dict[str, Any], tmp_path: Path
) -> None:
    single, on_album = _downloaded_on_a_single(fake_media)
    (tmp_path / "library" / Download.objects.get(track=single).file_path).unlink()

    _run(track_ids=[on_album.pk])

    assert fake_media["fetched"] != []
    assert Download.objects.filter(track=on_album).exists()


def test_another_recording_is_still_downloaded_from_youtube(fake_media: dict[str, Any]) -> None:
    _downloaded_on_a_single(fake_media)
    other = TrackFactory(duration=200)

    _run(track_ids=[other.pk])

    assert fake_media["fetched"] != []


def test_copy_measures_the_file_when_the_source_has_no_measure(fake_media: dict[str, Any]) -> None:
    single, on_album = _downloaded_on_a_single(fake_media)
    DownloadLoudness.objects.filter(download__track=single).delete()

    _run(track_ids=[on_album.pk])

    assert len(fake_media["measured"]) == 1
    assert DownloadLoudness.objects.filter(download__track=on_album).exists()
