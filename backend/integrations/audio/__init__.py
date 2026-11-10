"""Audio conversion and tagging."""

from .convert import FORMATS, convert
from .errors import AudioError, ConversionError, InvalidAudio
from .loudness import Loudness, measure_loudness, replaygain
from .naming import DEFAULT_TEMPLATE, PathIds, render_path, slug
from .tags import ReplayGain, Tags, write_tags
from .validate import AudioInfo, validate_audio

__all__ = [
    "DEFAULT_TEMPLATE",
    "FORMATS",
    "AudioError",
    "AudioInfo",
    "ConversionError",
    "InvalidAudio",
    "Loudness",
    "PathIds",
    "ReplayGain",
    "Tags",
    "convert",
    "measure_loudness",
    "render_path",
    "replaygain",
    "slug",
    "validate_audio",
    "write_tags",
]
