"""Tests for the daily technical-log purge."""

from datetime import timedelta

import pytest
from django.utils import timezone
from django_db_logger.models import StatusLog

import activity.tasks.purge as purge
from activity.models import ActivityLog
from jobs import scheduler

pytestmark = pytest.mark.django_db


def test_purge_is_registered_as_a_daily_periodic_job() -> None:
    periodic = scheduler._periodics["activity.purge_technical_logs"]

    assert periodic.interval == timedelta(days=1)


def test_daily_purge_deletes_old_technical_logs_and_records_it() -> None:
    old = StatusLog.objects.create(logger_name="x", level=20, msg="viejo")
    recent = StatusLog.objects.create(logger_name="x", level=20, msg="reciente")
    # ``create_datetime`` is set automatically on insert, so age the old row afterwards.
    StatusLog.objects.filter(pk=old.pk).update(create_datetime=timezone.now() - timedelta(days=60))

    purge._purge_daily()

    assert not StatusLog.objects.filter(pk=old.pk).exists()
    assert StatusLog.objects.filter(pk=recent.pk).exists()
    entry = ActivityLog.objects.get(action="activity.technical_logs.purged")
    assert entry.detail == {"deleted": 1}
