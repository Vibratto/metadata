"""Errors of the audio package."""


class AudioError(Exception):
    """Base audio error."""


class ConversionError(AudioError):
    """ffmpeg failed or is not available."""


class InvalidAudio(AudioError):
    """The file is not acceptable audio."""
