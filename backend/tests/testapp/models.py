"""Models that exist only for the tests."""

from django.db import models

from core.models import AppendOnlyModel


class Entry(AppendOnlyModel):
    """A minimal append-only record."""

    text = models.CharField(max_length=20)

    class Meta:
        app_label = "testapp"
