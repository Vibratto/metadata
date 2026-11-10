"""Tests for ``jobs`` models."""

import pytest
from django.utils import timezone

from core.models import AppendOnlyError
from jobs.models import JobRun

pytestmark = pytest.mark.django_db


def test_open_run_can_be_modified() -> None:
    run = JobRun.objects.create(kind="demo")
    run.done = 3
    run.save()
    run.refresh_from_db()
    assert run.done == 3
    assert not run.is_closed


def test_closed_run_cannot_be_modified() -> None:
    run = JobRun.objects.create(kind="demo")
    run.finished_at = timezone.now()
    run.save()
    run.done = 1
    with pytest.raises(AppendOnlyError):
        run.save()
    run.refresh_from_db()
    assert run.done == 0
    assert run.is_closed


def test_stale_copy_cannot_reopen_a_closed_run() -> None:
    run = JobRun.objects.create(kind="demo")
    stale = JobRun.objects.get(pk=run.pk)
    run.finished_at = timezone.now()
    run.save()
    with pytest.raises(AppendOnlyError):
        stale.save()


def test_str_shows_kind_and_id() -> None:
    run = JobRun.objects.create(kind="demo")
    assert str(run) == f"demo #{run.pk}"
