"""Tests for the ffmpeg conversion."""

import subprocess
from pathlib import Path

import mutagen
import pytest

from integrations.audio import FORMATS, ConversionError, convert


@pytest.mark.parametrize("fmt", sorted(FORMATS))
def test_converts_to_every_format(wav: Path, tmp_path: Path, fmt: str) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = convert(wav, out_dir, fmt, stem="song")
    assert result == out_dir / f"song.{FORMATS[fmt][0]}"
    assert mutagen.File(result) is not None


def test_stem_defaults_to_source_name(wav: Path, tmp_path: Path) -> None:
    assert convert(wav, tmp_path, "flac").name == "src.flac"


def test_unknown_format(wav: Path, tmp_path: Path) -> None:
    with pytest.raises(ConversionError, match="unsupported"):
        convert(wav, tmp_path, "wma")


def test_refuses_to_overwrite_source(wav: Path, tmp_path: Path) -> None:
    flac = convert(wav, tmp_path, "flac")
    with pytest.raises(ConversionError, match="same file"):
        convert(flac, tmp_path, "flac")


def test_ffmpeg_failure_removes_partial_output(tmp_path: Path) -> None:
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not audio")
    with pytest.raises(ConversionError):
        convert(bad, tmp_path, "mp3")
    assert not (tmp_path / "bad.mp3").exists()


def test_failure_without_stderr_reports_exit_code(
    wav: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 3, "", "")
    )
    with pytest.raises(ConversionError, match="exited with 3"):
        convert(wav, tmp_path, "mp3")


@pytest.mark.parametrize("error", [OSError("no ffmpeg"), subprocess.TimeoutExpired("ffmpeg", 1)])
def test_missing_binary_or_timeout(
    wav: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(ConversionError):
        convert(wav, tmp_path, "mp3")


def test_never_uses_shell(wav: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def spy(cmd: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen["cmd"], seen["kwargs"] = cmd, kwargs
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(subprocess, "run", spy)
    convert(wav, tmp_path, "mp3")
    assert isinstance(seen["cmd"], list)
    assert "shell" not in seen["kwargs"]  # type: ignore[operator]
