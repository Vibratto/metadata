"""Tests for upload validation."""

import wave
from pathlib import Path

import mutagen
import pytest

from integrations.audio import InvalidAudio, validate_audio


def test_valid_wav(wav: Path) -> None:
    info = validate_audio(wav)
    assert info.extension == ".wav" and info.size > 0 and 0.2 < info.duration < 0.4


def test_rejects_extension(tmp_path: Path) -> None:
    path = tmp_path / "x.exe"
    path.write_bytes(b"MZ")
    with pytest.raises(InvalidAudio, match="extension"):
        validate_audio(path)
    with pytest.raises(InvalidAudio, match="none"):
        validate_audio(tmp_path / "noext")


def test_rejects_empty_and_oversized(wav: Path, tmp_path: Path) -> None:
    empty = tmp_path / "e.mp3"
    empty.write_bytes(b"")
    with pytest.raises(InvalidAudio, match="empty or too large"):
        validate_audio(empty)
    with pytest.raises(InvalidAudio, match="empty or too large"):
        validate_audio(wav, max_bytes=10)


def test_rejects_renamed_non_audio(tmp_path: Path) -> None:
    path = tmp_path / "fake.mp3"
    path.write_bytes(b"this is text" * 100)
    with pytest.raises(InvalidAudio, match="readable"):
        validate_audio(path)


def test_rejects_zero_length_audio(tmp_path: Path) -> None:
    path = tmp_path / "zero.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
    with pytest.raises(InvalidAudio, match="readable"):
        validate_audio(path)


def test_mutagen_error_is_wrapped(wav: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(path: Path) -> None:
        raise mutagen.MutagenError("broken")

    monkeypatch.setattr(mutagen, "File", boom)
    with pytest.raises(InvalidAudio, match="readable"):
        validate_audio(wav)


def test_size_limit_is_inclusive(wav: Path) -> None:
    assert validate_audio(wav, max_bytes=wav.stat().st_size).size == wav.stat().st_size


def test_unrecognized_audio_is_rejected(wav: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mutagen, "File", lambda path: None)
    with pytest.raises(InvalidAudio, match="readable"):
        validate_audio(wav)
