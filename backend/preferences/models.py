"""``preferences`` app models."""

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from simple_history.models import HistoricalRecords

from .defaults import DEFAULTS


class Preference(models.Model):
    """Application setting stored as JSON.

    Editable, so every change is kept in the history table. Only keys declared
    in ``DEFAULTS`` are accepted.
    """

    key = models.CharField(gettext_lazy("key"), max_length=100, unique=True)
    value = models.JSONField(gettext_lazy("value"), null=True)
    updated_at = models.DateTimeField(gettext_lazy("updated"), auto_now=True)

    history = HistoricalRecords()

    class Meta:
        """Ordered by key."""

        ordering = ["key"]

    def __str__(self) -> str:
        """Returns the key."""
        return self.key

    def clean(self) -> None:
        """Rejects undeclared keys.

        Raises:
        """
        if self.key not in DEFAULTS:
            raise ValidationError({"key": _("Unknown setting key.")})


def get_value(key: str) -> Any:
    """Returns the stored value, or the code default when no row exists. A stored
    ``null`` is a real value: the row exists, so the default is not used.

    Args:

    Returns:
        The stored or default value.

    Raises:
    """
    if key not in DEFAULTS:
        raise KeyError(key)
    preference = Preference.objects.filter(key=key).first()
    return DEFAULTS[key] if preference is None else preference.value
