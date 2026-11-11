"""``jobs`` app models."""

from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import AppendOnlyError


class JobRun(models.Model):
    """One run of a background task. It is edited while it reports progress and
    sealed when ``finished_at`` is set: a closed run is history.
    """

    class Status(models.TextChoices):
        """Lifecycle of the run."""

        PENDING = "pending", _("pending")
        RUNNING = "running", _("running")
        STOPPING = "stopping", _("stopping")
        STOPPED = "stopped", _("stopped")
        SUCCEEDED = "succeeded", _("succeeded")
        FAILED = "failed", _("failed")
        INTERRUPTED = "interrupted", _("interrupted")

    #: States where the run still holds its kind.
    ACTIVE = (Status.PENDING, Status.RUNNING, Status.STOPPING)

    kind = models.CharField(_("kind"), max_length=50, db_index=True)
    params = models.JSONField(_("parameters"), default=dict, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="job_runs",
        verbose_name=_("user"),
    )
    status = models.CharField(
        _("status"), max_length=11, choices=Status.choices, default=Status.PENDING
    )
    started_at = models.DateTimeField(_("started"), default=timezone.now)
    finished_at = models.DateTimeField(_("finished"), null=True, blank=True)
    done = models.PositiveIntegerField(_("done"), default=0)
    total = models.PositiveIntegerField(_("total"), default=0)
    current = models.CharField(_("current item"), max_length=255, blank=True)
    summary = models.JSONField(_("summary"), default=dict, blank=True)

    class Meta:
        """Most recent first."""

        ordering = ["-started_at", "-id"]

    def __str__(self) -> str:
        """Returns kind and id."""
        return f"{self.kind} #{self.pk}"

    @property
    def is_closed(self) -> bool:
        """Whether the run has ended."""
        return self.finished_at is not None

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Saves only while the stored row is still open. The check reads the
        database, not ``self``, so a stale copy cannot reopen a closed run.
        """
        if (
            not self._state.adding
            and JobRun.objects.filter(pk=self.pk, finished_at__isnull=False).exists()
        ):
            raise AppendOnlyError("A finished run cannot be modified.")
        super().save(*args, **kwargs)
