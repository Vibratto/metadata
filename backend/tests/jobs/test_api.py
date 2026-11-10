"""Task API tests."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from activity.models import ActivityLog
from jobs import registry, runner
from jobs.models import JobRun, JobRunLine

pytestmark = pytest.mark.django_db
BASE = "/api/v1/jobs/runs/"


@pytest.fixture(autouse=True)
def demo_task(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isolated registry with one task."""
    monkeypatch.setattr(registry, "_tasks", {})

    @registry.register("demo")
    def task(run: JobRun, params: dict[str, Any]) -> dict[str, Any]:
        runner.line(run, JobRunLine.Level.INFO, "uno")
        runner.line(run, JobRunLine.Level.WARNING, "dos")
        return {"echo": params}

    yield


def test_anonymous_is_rejected() -> None:
    assert APIClient().get(BASE).status_code == 403
    assert APIClient().post(BASE, {"kind": "demo"}, format="json").status_code == 403


def test_start_runs_task_and_logs_activity(api: APIClient) -> None:
    response = api.post(BASE, {"kind": "demo", "params": {"a": 1}}, format="json")
    assert response.status_code == 201
    assert response.data["status"] == "succeeded"
    assert response.data["user"] == "owner"
    assert response.data["summary"] == {"echo": {"a": 1}}
    assert ActivityLog.objects.filter(action="jobs.run.started", username="owner").count() == 1


@pytest.mark.parametrize("body", [{"kind": "nope"}, {}, {"kind": "demo", "params": [1]}])
def test_start_rejects_invalid_requests(api: APIClient, body: dict[str, Any]) -> None:
    assert api.post(BASE, body, format="json").status_code == 400
    assert not JobRun.objects.exists()


def test_start_conflicts_when_kind_is_active(api: APIClient) -> None:
    JobRun.objects.create(kind="demo", status=JobRun.Status.RUNNING)
    assert api.post(BASE, {"kind": "demo"}, format="json").status_code == 409


def test_list_is_paginated_and_filtered(api: APIClient) -> None:
    old = JobRun.objects.create(kind="demo", started_at=timezone.now() - timedelta(days=3))
    JobRun.objects.filter(pk=old.pk).update(status=JobRun.Status.FAILED)
    recent = JobRun.objects.create(kind="other", status=JobRun.Status.SUCCEEDED)

    assert api.get(BASE).data["count"] == 2
    assert [r["id"] for r in api.get(BASE, {"kind": "other"}).data["results"]] == [recent.pk]
    assert [r["id"] for r in api.get(BASE, {"status": "failed"}).data["results"]] == [old.pk]
    since = (timezone.now() - timedelta(days=1)).isoformat()
    assert [r["id"] for r in api.get(BASE, {"started_after": since}).data["results"]] == [recent.pk]
    assert api.get(BASE, {"started_before": since}).data["count"] == 1


def test_detail_shows_progress(api: APIClient) -> None:
    run = JobRun.objects.create(kind="demo", done=2, total=5, current="x")
    data = api.get(f"{BASE}{run.pk}/").data
    assert (data["done"], data["total"], data["current"], data["user"]) == (2, 5, "x", None)
    assert api.get(f"{BASE}999/").status_code == 404


def test_lines_are_returned_after_a_position(api: APIClient) -> None:
    run = JobRun.objects.get(pk=api.post(BASE, {"kind": "demo"}, format="json").data["id"])
    assert [line["message"] for line in api.get(f"{BASE}{run.pk}/lines/").data] == ["uno", "dos"]
    after = api.get(f"{BASE}{run.pk}/lines/", {"after": 1}).data
    assert [(line["position"], line["level"]) for line in after] == [(2, "warning")]
    assert api.get(f"{BASE}{run.pk}/lines/", {"after": "x"}).status_code == 400


def test_stop_requests_stop_and_logs_activity(api: APIClient) -> None:
    run = JobRun.objects.create(kind="demo", status=JobRun.Status.RUNNING)
    response = api.post(f"{BASE}{run.pk}/stop/")
    assert response.status_code == 200
    assert response.data["status"] == "stopping"
    assert ActivityLog.objects.filter(action="jobs.run.stop_requested").count() == 1


def test_stop_of_closed_run_conflicts(api: APIClient) -> None:
    run = JobRun.objects.create(kind="demo", status=JobRun.Status.SUCCEEDED)
    JobRun.objects.filter(pk=run.pk).update(finished_at=timezone.now())
    assert api.post(f"{BASE}{run.pk}/stop/").status_code == 409
    assert not ActivityLog.objects.filter(action="jobs.run.stop_requested").exists()


def test_runs_cannot_be_edited_or_deleted(api: APIClient) -> None:
    run = JobRun.objects.create(kind="demo")
    assert api.patch(f"{BASE}{run.pk}/", {"kind": "x"}, format="json").status_code == 405
    assert api.delete(f"{BASE}{run.pk}/").status_code == 405
