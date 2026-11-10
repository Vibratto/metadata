"""Manual audio upload tests."""

import math
import struct
import wave
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from activity.models import ActivityLog
from catalog import upload
from catalog.factories import TrackFactory
from catalog.models import Download, DownloadLoudness
from catalog.services import library, replaygain
from integrations.audio import ConversionError, Loudness, slug
from integrations.lrclib import Lyrics
from preferences.models import Preference

from .conftest import FakeLrclib

pytestmark = pytest.mark.django_db


def _wav() -> bytes:
    """0.3 s WAV with a tone."""
    buffer = BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(
            b"".join(struct.pack("<h", int(8000 * math.sin(i / 5))) for i in range(2400))
        )
    return buffer.getvalue()


def _file(name: str = "recording.wav", content: bytes | None = None) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, _wav() if content is None else content, "audio/wav")


@pytest.fixture(autouse=True)
def fake_media(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Replaces ffmpeg and tag writing; returns what they were asked."""
    calls: dict[str, Any] = {"converted": [], "tagged": []}
    Preference.objects.create(key="download.folder", value=str(tmp_path / "library"))

    def to_format(source: Path, dest_dir: Path, fmt: str, *, stem: str | None = None) -> Path:
        calls["converted"].append(source.read_bytes())
        out = dest_dir / f"{stem or source.stem}.{fmt}"
        out.write_bytes(b"audio")
        return out

    monkeypatch.setattr(upload, "convert", to_format)
    monkeypatch.setattr(library, "write_tags", lambda path, tags: calls["tagged"].append(tags))
    monkeypatch.setattr(
        replaygain, "measure_loudness", lambda paths: Loudness(lufs=-20.0, peak=0.5)
    )
    return calls


def _url(pk: int) -> str:
    return f"/api/v1/catalog/tracks/{pk}/upload/"


def test_converts_tags_stores_and_records(
    api: APIClient, fake_media: dict[str, Any], tmp_path: Path
) -> None:
    track = TrackFactory(title="Song")
    response = api.post(_url(track.pk), {"file": _file()}, format="multipart")

    assert response.status_code == 201
    assert response.data["id"] == track.pk
    assert response.data["downloaded"] is True
    download = Download.objects.get(track=track)
    assert download.file_path.endswith(f"-song-{track.pk}.mp3")
    assert not Path(download.file_path).is_absolute()
    assert (tmp_path / "library" / download.file_path).read_bytes() == b"audio"
    assert download.audio_format == "mp3"
    # No source URL: that is what tells an upload from a download.
    assert download.source_url == ""
    assert fake_media["converted"] == [_wav()]
    assert fake_media["tagged"][0].title == "Song"
    log = ActivityLog.objects.get(action="catalog.track.uploaded")
    assert log.detail == {"file_path": download.file_path, "audio_format": "mp3"}


def test_upload_measures_the_track(api: APIClient, fake_media: dict[str, Any]) -> None:
    track = TrackFactory()
    api.post(_url(track.pk), {"file": _file()}, format="multipart")
    stored = DownloadLoudness.objects.get(download__track=track)
    assert (stored.lufs, stored.peak) == (-20.0, 0.5)
    assert fake_media["tagged"][0].replaygain.track_gain_db == 2.0


def test_respects_format_and_template_preferences(api: APIClient) -> None:
    Preference.objects.create(key="download.format", value="flac")
    Preference.objects.create(key="download.name_template", value="{album}/{title}")
    track = TrackFactory(title="Song")
    api.post(_url(track.pk), {"file": _file()}, format="multipart")
    download = Download.objects.get(track=track)
    assert download.audio_format == "flac"
    assert download.file_path == f"{slug(track.album.title, track.album.pk)}/song-{track.pk}.flac"


@pytest.mark.parametrize(
    "file",
    [
        pytest.param(lambda: _file("notas.txt", b"hola"), id="extension"),
        pytest.param(lambda: _file("falso.mp3", b"no soy audio"), id="not-audio"),
    ],
)
def test_rejects_invalid_file(api: APIClient, file: Any, fake_media: dict[str, Any]) -> None:
    track = TrackFactory()
    response = api.post(_url(track.pk), {"file": file()}, format="multipart")
    assert response.status_code == 400
    assert "file" in response.data
    assert not Download.objects.exists()
    assert fake_media["converted"] == []


def test_rejects_too_large_file(api: APIClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload, "MAX_BYTES", 100)
    response = api.post(_url(TrackFactory().pk), {"file": _file()}, format="multipart")
    assert response.status_code == 400
    assert "file" in response.data


def test_rejects_missing_file(api: APIClient) -> None:
    response = api.post(_url(TrackFactory().pk), {}, format="multipart")
    assert response.status_code == 400
    assert "file" in response.data


def test_conversion_failure_leaves_nothing(
    api: APIClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def broken(*args: Any, **kwargs: Any) -> Path:
        raise ConversionError("boom")

    monkeypatch.setattr(upload, "convert", broken)
    response = api.post(_url(TrackFactory().pk), {"file": _file()}, format="multipart")
    assert response.status_code == 422
    assert "detail" in response.data
    assert not Download.objects.exists()
    assert not (tmp_path / "library").exists()
    assert not ActivityLog.objects.filter(action="catalog.track.uploaded").exists()


def test_unknown_track_is_404(api: APIClient) -> None:
    assert api.post(_url(999), {"file": _file()}, format="multipart").status_code == 404


def test_anonymous_cannot_upload(db: None) -> None:
    track = TrackFactory()
    response = APIClient().post(_url(track.pk), {"file": _file()}, format="multipart")
    assert response.status_code in (401, 403)


def test_rejects_oversized_request_before_reading_it(
    api: APIClient, monkeypatch: pytest.MonkeyPatch, fake_media: dict[str, Any]
) -> None:
    monkeypatch.setattr(upload, "MAX_BYTES", 100)
    track = TrackFactory()
    # Declared length above the limit plus the multipart margin: nothing gets parsed.
    too_big = str(100 + upload.MULTIPART_OVERHEAD + 1)
    response = api.post(
        _url(track.pk), {"file": _file()}, format="multipart", CONTENT_LENGTH=too_big
    )
    assert response.status_code == 413
    assert fake_media["converted"] == []
    assert not Download.objects.exists()


def test_saves_the_lyrics_next_to_the_uploaded_audio(
    api: APIClient, lrclib: FakeLrclib, tmp_path: Path
) -> None:
    lrclib.answer = Lyrics(synced=None, plain="Hello\n", instrumental=False)
    track = TrackFactory(title="Song", duration=200)

    api.post(_url(track.pk), {"file": _file()}, format="multipart")

    audio = tmp_path / "library" / Download.objects.get(track=track).file_path
    assert audio.with_suffix(".lrc").read_text(encoding="utf-8") == "Hello\n"


def test_lyrics_failure_does_not_fail_the_upload(api: APIClient, lrclib: FakeLrclib) -> None:
    lrclib.answer = requests.ConnectionError("LRCLIB is down")
    track = TrackFactory(title="Song", duration=200)

    response = api.post(_url(track.pk), {"file": _file()}, format="multipart")

    assert response.status_code == 201
    assert Download.objects.filter(track=track).exists()


def test_upload_does_not_look_up_lyrics_when_turned_off(api: APIClient, lrclib: FakeLrclib) -> None:
    Preference.objects.create(key="lyrics.enabled", value=False)
    api.post(_url(TrackFactory(duration=200).pk), {"file": _file()}, format="multipart")
    assert lrclib.asked == []
