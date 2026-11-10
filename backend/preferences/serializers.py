"""Serializers of the settings API."""

from collections.abc import Callable
from typing import Any

from django.utils.translation import gettext as _
from rest_framework import serializers

from integrations.audio import FORMATS, PathIds, Tags, render_path

from .defaults import DEFAULTS

_SAMPLE = Tags(
    title="t", artists=("a",), album="b", album_artists=("a",), track_number=1, disc_number=1,
    year=2000,
)  # fmt: skip
_SAMPLE_IDS = PathIds(track=1, album=2, artist=3, album_artist=3)


def _check_template(value: str) -> None:
    """Try the naming template on a sample track.

    The folders must include ``{album}``, so each folder holds a single album and its
    ``cover.jpg`` belongs to it, and the file name must include ``{title}`` or ``{track}``.
    """
    folders, _sep, name = value.rpartition("/")
    if "{album}" not in folders or ("{title}" not in name and "{track}" not in name):
        raise serializers.ValidationError(
            _("The template needs {album} in its folders and {title} or {track} in the file name.")
        )
    try:
        render_path(value, _SAMPLE, _SAMPLE_IDS, "mp3")
    except (KeyError, ValueError, IndexError, AttributeError) as error:
        raise serializers.ValidationError(_("The template is not valid.")) from error


def _check_format(value: str) -> None:
    if value not in FORMATS:
        raise serializers.ValidationError(_("Unsupported format: %(value)s.") % {"value": value})


def _check_separators(value: list[Any]) -> None:
    """Between 1 and 20 distinct, non-blank, short texts.

    The spaces around a separator are part of it (`` / `` is not ``/``), so values are
    kept as sent. Blank ones are refused because they would split every name.
    """
    if not 1 <= len(value) <= 20:
        raise serializers.ValidationError(_("Between 1 and 20 separators are needed."))
    if not all(isinstance(item, str) and item.strip() and len(item) <= 10 for item in value):
        raise serializers.ValidationError(
            _("Each separator must be a non-blank text of at most 10 characters.")
        )
    if len(set(value)) != len(value):
        raise serializers.ValidationError(_("A separator is listed twice."))


def _check_threshold(value: int) -> None:
    if value < 0:
        raise serializers.ValidationError(_("The threshold cannot be negative."))


# Settings used as they are: a bad value would break every download or suggestion.
_CHECKS: dict[str, Callable[[Any], None]] = {
    "download.format": _check_format,
    "download.name_template": _check_template,
    "tags.artist_separators": _check_separators,
    "import.suggestion_threshold": _check_threshold,
}


class PreferenceSerializer(serializers.Serializer[dict[str, Any]]):
    """A setting with its effective and default values."""

    key = serializers.CharField(read_only=True)
    value = serializers.JSONField(read_only=True)
    default = serializers.JSONField(read_only=True)


class PreferenceWriteSerializer(serializers.Serializer[dict[str, Any]]):
    """New value for a setting.

    Only the type of the default is accepted, so a setting never changes shape and the
    code reading it needs no defensive parsing.
    """

    value = serializers.JSONField()

    def validate_value(self, value: Any) -> Any:
        expected = type(DEFAULTS[self.context["key"]])
        if type(value) is not expected:
            raise serializers.ValidationError(
                _("The value must be of type %(type)s.") % {"type": expected.__name__}
            )
        if check := _CHECKS.get(self.context["key"]):
            check(value)
        return value
