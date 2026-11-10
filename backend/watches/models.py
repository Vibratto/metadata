"""Models of the ``watches`` app."""

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from catalog.models import Artist
from core.models import AppendOnlyModel


class Watch(models.Model):
    """A new-release watch: its artists, how often to check, and what to do with finds."""

    name = models.CharField(_("name"), max_length=120, unique=True)
    enabled = models.BooleanField(_("enabled"), default=True)
    interval_hours = models.PositiveSmallIntegerField(
        _("interval (hours)"), default=24, validators=[MinValueValidator(1)]
    )
    auto_download = models.BooleanField(_("automatic download"), default=False)
    # Defaults to now: a new watch is checked on the scheduler's next pass.
    next_run_at = models.DateTimeField(_("next check"), default=timezone.now, db_index=True)
    artists = models.ManyToManyField(
        Artist, through="WatchArtist", related_name="watches", verbose_name=_("artists")
    )
    created_at = models.DateTimeField(_("created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WatchArtist(models.Model):
    """An artist under watch and its position in the watch's list."""

    watch = models.ForeignKey(Watch, on_delete=models.CASCADE, related_name="watch_artists")
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name="watch_entries")
    position = models.PositiveSmallIntegerField(_("position"), default=0)

    class Meta:
        ordering = ["watch", "position"]
        constraints = [
            models.UniqueConstraint(fields=["watch", "artist"], name="unique_watch_artist")
        ]

    def __str__(self) -> str:
        return f"{self.watch} / {self.artist}"


class WatchRun(AppendOnlyModel):
    """The outcome of one new-release check.

    Written once, when the check finishes, which is what lets it be append-only.
    """

    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", _("succeeded")
        FAILED = "failed", _("failed")

    watch = models.ForeignKey(
        Watch, on_delete=models.PROTECT, related_name="runs", verbose_name=_("watch")
    )
    started_at = models.DateTimeField(_("started"), default=timezone.now)
    finished_at = models.DateTimeField(_("finished"), default=timezone.now)
    status = models.CharField(_("status"), max_length=10, choices=Status.choices)
    found = models.PositiveIntegerField(_("new releases found"), default=0)
    detail = models.TextField(_("detail"), blank=True)

    class Meta:
        ordering = ["-finished_at", "-id"]
