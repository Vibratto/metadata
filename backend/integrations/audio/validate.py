"""Validation of a hand-uploaded audio file."""

from dataclasses import dataclass
from pathlib import Path

import mutagen

from .errors import InvalidAudio

ALLOWED_EXTENSIONS = frozenset({".mp3", ".m4a", ".flac", ".opus", ".ogg", ".wav"})
MAX_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class AudioInfo:
    """Technical data of a valid audio file."""

    extension: str
    duration: float
    size: int


def validate_audio(path: Path, *, max_bytes: int = MAX_BYTES) -> AudioInfo:
    """Checks extension, size, and that mutagen recognizes it as audio, so a renamed
    non-audio file is rejected instead of being trusted by its name.

    Args:
        path: File to check.
        max_bytes: Maximum size.

    Returns:
        Extension, duration in seconds, size.

    Raises:
        InvalidAudio: If any check fails.
    """
    extension = path.suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise InvalidAudio(f"extension not allowed: {extension or 'none'}")
    size = path.stat().st_size
    if size == 0 or size > max_bytes:
        raise InvalidAudio("file is empty or too large")
    try:
        audio = mutagen.File(path)
    except mutagen.MutagenError as exc:
        raise InvalidAudio("not a readable audio file") from exc
    if audio is None or audio.info is None or not audio.info.length:
        raise InvalidAudio("not a readable audio file")
    return AudioInfo(extension=extension, duration=float(audio.info.length), size=size)
