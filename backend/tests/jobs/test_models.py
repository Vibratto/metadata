"""Tests for ``jobs`` models."""

import pytest
from django.utils import timezone

from core.models import AppendOnlyError
from jobs.models import JobRun, JobRunLine

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


def test_line_cannot_be_modified_or_deleted() -> None:
    run = JobRun.objects.create(kind="demo")
    line = JobRunLine.objects.create(run=run, position=1, message="hola")
    line.message = "otra"
    with pytest.raises(AppendOnlyError):
        line.save()
    with pytest.raises(AppendOnlyError):
        line.delete()
    with pytest.raises(AppendOnlyError):
        JobRunLine.objects.all().update(**{"message": "x"})
    with pytest.raises(AppendOnlyError):
        JobRunLine.objects.all().delete()


def test_line_position_is_unique_per_run() -> None:
    run = JobRun.objects.create(kind="demo")
    JobRunLine.objects.create(run=run, position=1, message="a")
    with pytest.raises(Exception, match="UNIQUE|unique"):
        JobRunLine.objects.create(run=run, position=1, message="b")
