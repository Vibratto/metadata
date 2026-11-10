"""Activity and technical log tests."""

import logging
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from django_db_logger.models import StatusLog

from activity.logs import current_job_id, redact
from activity.models import ActivityLog
from activity.services import log_activity, purge_technical_logs
from core.models import AppendOnlyError

pytestmark = pytest.mark.django_db


def test_log_activity_records_user_object_and_detail() -> None:
    user = get_user_model().objects.create_user("ana")
    entry = log_activity(user, "auth.login", obj=user, detail={"ip": "10.0.0.1"})
    entry.refresh_from_db()
    assert (entry.user, entry.username, entry.action) == (user, "ana", "auth.login")
    assert entry.target == user
    assert entry.detail == {"ip": "10.0.0.1"}


@pytest.mark.parametrize("actor", [None, AnonymousUser()])
def test_log_activity_without_authenticated_user(actor: AnonymousUser | None) -> None:
    entry = log_activity(actor, "system.start")
    assert (entry.user, entry.username, entry.target, entry.detail) == (None, "", None, {})


def test_log_activity_survives_user_deletion() -> None:
    user = get_user_model().objects.create_user("ana")
    entry = log_activity(user, "auth.login")
    user.delete()
    entry.refresh_from_db()
    assert entry.user is None
    assert entry.username == "ana"


def test_log_activity_redacts_sensitive_detail() -> None:
    entry = log_activity(None, "auth.change", detail={"password": "hunter2", "ok": 1})
    assert entry.detail == {"password": "***", "ok": 1}


def test_activity_log_is_append_only() -> None:
    entry = log_activity(None, "a")
    entry.action = "b"
    with pytest.raises(AppendOnlyError):
        entry.save()
    with pytest.raises(AppendOnlyError):
        entry.delete()
    with pytest.raises(AppendOnlyError):
        ActivityLog.objects.update(action="b")
    with pytest.raises(AppendOnlyError):
        ActivityLog.objects.all().delete()


def test_purge_keeps_recent_and_deletes_old_logs() -> None:
    old = StatusLog.objects.create(logger_name="x", msg="old")
    StatusLog.objects.create(logger_name="x", msg="new")
    StatusLog.objects.filter(pk=old.pk).update(create_datetime=timezone.now() - timedelta(days=31))
    assert purge_technical_logs() == 1
    assert list(StatusLog.objects.values_list("msg", flat=True)) == ["new"]


def test_purge_never_touches_activity_log() -> None:
    log_activity(None, "a")
    purge_technical_logs(days=0)
    assert ActivityLog.objects.count() == 1


def test_db_handler_stores_job_id() -> None:
    token = current_job_id.set("42")
    try:
        logging.getLogger("tests.job").warning("hecho")
    finally:
        current_job_id.reset(token)
    assert StatusLog.objects.get(logger_name="tests.job").msg == "[job 42] hecho"


@pytest.mark.parametrize(
    "message",
    [
        "login password=hunter2 ok",
        'payload {"token": "hunter2"}',
        "Cookie: hunter2",
        "Authorization: hunter2",
        "sessionid=hunter2&next=/",
        "csrftoken=hunter2",
    ],
)
def test_sensitive_data_never_reaches_database_or_console(
    message: str, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    logger = logging.getLogger("tests.secret")
    logger.error(message)
    logger.error("arg %s", message)
    assert StatusLog.objects.count() == 2
    for row in StatusLog.objects.all():
        assert "hunter2" not in row.msg
        assert "***" in row.msg
    assert "hunter2" not in capsys.readouterr().err


def test_redact_nested_and_non_string_values() -> None:
    value = {"a": [{"Authorization": "x", "n": 3}], "k": ("password=1",), "none": None}
    assert redact(value) == {
        "a": [{"Authorization": "***", "n": 3}],
        "k": ["password=***"],
        "none": None,
    }


def test_redact_hides_credentials_inside_urls() -> None:
    """A proxy written as ``user:password@host`` leaves no password in the logs."""
    text = "No conecta con http://bob:s3cr3t@10.0.0.1:8080 y socks5h://ana:otra@h:1080"

    cleaned = redact(text)

    assert "s3cr3t" not in cleaned
    assert "otra" not in cleaned
    assert "http://***@10.0.0.1:8080" in cleaned
    assert redact("https://example.com/a@b") == "https://example.com/a@b"
