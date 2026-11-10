"""Activity and technical log API."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from django_db_logger.models import StatusLog
from rest_framework.test import APIClient

from activity.models import ActivityLog
from activity.services import log_activity
from core.models import AppendOnlyError

pytestmark = pytest.mark.django_db

ENTRIES = "/api/v1/activity/entries/"
LOGS = "/api/v1/activity/logs/"


@pytest.mark.parametrize("url", [ENTRIES, LOGS])
def test_a_session_is_required(anonymous: APIClient, url: str) -> None:
    assert anonymous.get(url).status_code == 403


def test_entry_has_user_action_object_and_detail(api: APIClient, owner: User) -> None:
    log_activity(owner, "catalog.artist.blocked", obj=owner, detail={"reason": "x"})
    row = api.get(ENTRIES).json()["results"][0]
    assert row["action"] == "catalog.artist.blocked"
    assert row["username"] == "owner"
    assert row["object_type"] == "auth.user"
    assert row["object_id"] == str(owner.pk)
    assert row["detail"] == {"reason": "x"}


@pytest.fixture
def three_entries(owner: User) -> list[ActivityLog]:
    """One entry by the owner, ten days old, and two recent ones by the system."""
    old = timezone.now() - timedelta(days=10)
    with patch("django.utils.timezone.now", return_value=old):
        first = log_activity(owner, "catalog.artist.blocked", obj=owner)
    return [
        first,
        log_activity(None, "catalog.album.edited"),
        log_activity(None, "watches.watch.checked"),
    ]


RECENT = {"catalog.album.edited", "watches.watch.checked"}
FIVE_DAYS_AGO = (timezone.now() - timedelta(days=5)).date().isoformat()


@pytest.mark.parametrize(
    ("query", "expected_actions"),
    [
        ({"username": "owner"}, {"catalog.artist.blocked"}),
        ({"action": "blocked"}, {"catalog.artist.blocked"}),
        ({"object_type": "auth.user"}, {"catalog.artist.blocked"}),
        ({"date_from": FIVE_DAYS_AGO}, RECENT),
        ({"date_to": FIVE_DAYS_AGO}, {"catalog.artist.blocked"}),
    ],
)
@pytest.mark.usefixtures("three_entries")
def test_entries_are_filtered(
    api: APIClient, query: dict[str, str], expected_actions: set[str]
) -> None:
    rows = api.get(ENTRIES, query).json()["results"]
    assert {row["action"] for row in rows} == expected_actions


@pytest.mark.usefixtures("three_entries")
def test_entries_are_filtered_by_user_id(api: APIClient, owner: User) -> None:
    rows = api.get(ENTRIES, {"user": owner.pk}).json()["results"]
    assert [row["action"] for row in rows] == ["catalog.artist.blocked"]


def test_malformed_date_is_a_400(api: APIClient) -> None:
    assert api.get(ENTRIES, {"date_from": "yesterday"}).status_code == 400


def test_entries_are_read_only(api: APIClient, three_entries: list[ActivityLog]) -> None:
    url = f"{ENTRIES}{three_entries[0].pk}/"
    assert api.delete(url).status_code == 405
    assert api.patch(url, {"action": "x"}, format="json").status_code == 405
    with pytest.raises(AppendOnlyError):
        three_entries[0].delete()


def test_logs_are_filtered_and_searched(api: APIClient) -> None:
    StatusLog.objects.create(logger_name="jobs.runner", level=40, msg="[job 7] network failure")
    StatusLog.objects.create(logger_name="accounts", level=20, msg="[job 3] started")
    StatusLog.objects.create(logger_name="jobs.runner", level=30, msg="no job")

    def messages(query: dict[str, str | int]) -> set[str]:
        return {row["msg"] for row in api.get(LOGS, query).json()["results"]}

    assert messages({"min_level": 30}) == {"[job 7] network failure", "no job"}
    assert messages({"module": "accounts"}) == {"[job 3] started"}
    assert messages({"search": "NETWORK"}) == {"[job 7] network failure"}
    assert messages({"task": 7}) == {"[job 7] network failure"}
    assert len(messages({"date_from": timezone.now().date().isoformat()})) == 3


def test_logs_are_read_only(api: APIClient) -> None:
    entry = StatusLog.objects.create(logger_name="x", level=20, msg="m")
    url = f"{LOGS}{entry.pk}/"
    assert api.get(url).json()["msg"] == "m"
    assert api.delete(url).status_code == 405
    assert api.patch(url, {"msg": "n"}, format="json").status_code == 405
