"""Library ReplayGain tests."""

import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from mutagen.flac import FLAC

from catalog.factories import AlbumFactory, DownloadFactory, TrackFactory
from catalog.models import AlbumLoudness, Download, DownloadLoudness
from catalog.services import replaygain as service
from integrations.audio import Loudness, measure_loudness
from preferences.models import Preference

pytestmark = pytest.mark.django_db


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """Library folder."""
    folder = tmp_path / "lib"
    folder.mkdir()
    Preference.objects.create(key="download.folder", value=str(folder))
    return folder


def _tone(path: Path, amplitude: float) -> None:
    subprocess.run(  # noqa: S603
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi",  # noqa: S607
         "-i", f"aevalsrc={amplitude}*sin(2*PI*1000*t):s=48000:d=2", str(path)],
        check=True,
    )  # fmt: skip


def _download(library: Path, track: Any, name: str, amplitude: float | None = 0.5) -> Download:
    """Download with a real tone in the library."""
    if amplitude is not None:
        _tone(library / name, amplitude)
    return cast(Download, DownloadFactory(track=track, file_path=name, audio_format="flac"))


def test_measure_honours_the_preference(library: Path) -> None:
    _tone(library / "a.flac", 0.5)
    assert service.measure(library / "a.flac") == measure_loudness([library / "a.flac"])
    Preference.objects.create(key="replaygain.enabled", value=False)
    assert service.measure(library / "a.flac") is None


def test_remember_stores_and_replaces_the_measure() -> None:
    download = DownloadFactory()
    service.remember(download, None)
    assert not DownloadLoudness.objects.exists()
    service.remember(download, Loudness(lufs=-9.0, peak=0.5))
    service.remember(download, Loudness(lufs=-10.0, peak=0.4))
    stored = DownloadLoudness.objects.get(download=download)
    assert (stored.lufs, stored.peak) == (-10.0, 0.4)


def test_album_gain_is_measured_over_the_union_and_written_to_every_track(library: Path) -> None:
    album = AlbumFactory()
    first = TrackFactory(album=album, disc_number=1, track_number=1)
    second = TrackFactory(album=album, disc_number=1, track_number=2)
    _download(library, first, "1.flac", 0.5)
    _download(library, second, "2.flac", 0.05)

    assert service.update_album(album) == 2

    union = measure_loudness([library / "1.flac", library / "2.flac"])
    alone = measure_loudness([library / "2.flac"])
    stored = AlbumLoudness.objects.get(album=album)
    assert (stored.lufs, stored.peak) == (union.lufs, union.peak)
    for name in ("1.flac", "2.flac"):
        assert FLAC(library / name)["replaygain_album_gain"] == [f"{-18 - union.lufs:.2f} dB"]
    flac = FLAC(library / "2.flac")
    assert flac["replaygain_track_gain"] == [f"{-18 - alone.lufs:.2f} dB"]
    assert flac["title"] == [second.title]
    assert DownloadLoudness.objects.count() == 2


def test_album_uses_each_tracks_latest_file_and_skips_missing_ones(library: Path) -> None:
    album = AlbumFactory()
    track = TrackFactory(album=album)
    old = _download(library, track, "old.flac", 0.05)
    _download(library, track, "new.flac", 0.5)
    _download(library, TrackFactory(album=album), "gone.flac", None)

    assert service.update_album(album) == 1

    assert (
        AlbumLoudness.objects.get(album=album).lufs == measure_loudness([library / "new.flac"]).lufs
    )
    assert "replaygain_album_gain" not in FLAC(library / "old.flac")
    assert not DownloadLoudness.objects.filter(download=old).exists()


def test_album_without_files_is_left_alone(library: Path) -> None:
    album = AlbumFactory()
    _download(library, TrackFactory(album=album), "gone.flac", None)
    assert service.update_album(album) == 0
    assert not AlbumLoudness.objects.exists()


def test_stored_track_measures_are_reused_unless_remeasuring(
    library: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    album = AlbumFactory()
    download = _download(library, TrackFactory(album=album), "1.flac")
    DownloadLoudness.objects.create(download=download, lufs=-30.0, peak=0.1)

    service.update_album(album)
    assert FLAC(library / "1.flac")["replaygain_track_gain"] == ["12.00 dB"]

    service.update_album(album, remeasure=True)
    real = measure_loudness([library / "1.flac"])
    assert DownloadLoudness.objects.get(download=download).lufs == real.lufs


def test_album_rewrite_keeps_the_embedded_cover_when_asked(library: Path) -> None:
    Preference.objects.create(key="tags.embed_cover", value=True)
    album = AlbumFactory()
    _download(library, TrackFactory(album=album), "1.flac")
    (library / "cover.jpg").write_bytes(b"\xff\xd8jpeg")

    service.update_album(album)

    assert FLAC(library / "1.flac").pictures[0].data == b"\xff\xd8jpeg"
