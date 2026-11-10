"""Signing in and out, the session, and changing credentials."""

from datetime import timedelta
from importlib.util import find_spec
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Profile
from activity.models import ActivityLog
from tests.conftest import PASSWORD

pytestmark = pytest.mark.django_db

BASE = "/api/v1/accounts"
LOGIN = f"{BASE}/login/"
ME = f"{BASE}/me/"
GOOD = {"username": "owner", "password": PASSWORD}
BAD = {"username": "owner", "password": "wrong"}
NEW_PASSWORD = "another-long-password-77"


def test_sign_in_opens_a_session_and_returns_the_profile(anonymous: APIClient, owner: User) -> None:
    response = anonymous.post(LOGIN, GOOD)
    assert response.status_code == 200
    assert response.json() == {"username": "owner", "language": "", "failed_attempts": 0}
    assert anonymous.get(ME).status_code == 200


def test_sign_in_reports_the_failures_that_came_before_it(
    anonymous: APIClient, owner: User
) -> None:
    # axes clears them on success, so this response is the only place to learn of them.
    for _ in range(2):
        anonymous.post(LOGIN, BAD)
    assert anonymous.post(LOGIN, GOOD).json()["failed_attempts"] == 2


def test_wrong_password_and_unknown_user_look_the_same(anonymous: APIClient, owner: User) -> None:
    wrong_password = anonymous.post(LOGIN, BAD)
    unknown_user = anonymous.post(LOGIN, {"username": "nobody", "password": "wrong"})
    assert wrong_password.status_code == unknown_user.status_code == 400
    assert wrong_password.json() == unknown_user.json()
    assert wrong_password.json() == {"detail": "Wrong username or password."}


def test_sign_in_enforces_csrf(owner: User) -> None:
    assert APIClient(enforce_csrf_checks=True).post(LOGIN, GOOD).status_code == 403


def test_sign_in_accepts_the_csrf_token_in_a_header(owner: User) -> None:
    client = APIClient(enforce_csrf_checks=True)
    token = client.get(f"{BASE}/setup/").cookies["csrftoken"].value
    assert client.post(LOGIN, GOOD, headers={"x-csrftoken": token}).status_code == 200


def test_too_many_failures_lock_the_account_out(anonymous: APIClient, owner: User) -> None:
    for _ in range(5):
        anonymous.post(LOGIN, BAD)
    assert anonymous.post(LOGIN, GOOD).status_code == 429


def test_behind_a_trusted_proxy_lockout_follows_the_real_address(
    anonymous: APIClient, owner: User, settings: Any
) -> None:
    assert find_spec("ipware"), "django-ipware is missing: pip install -r requirements.txt"
    settings.AXES_IPWARE_PROXY_ORDER = "right-most"
    settings.AXES_IPWARE_META_PRECEDENCE_ORDER = ["HTTP_X_FORWARDED_FOR"]
    for _ in range(5):
        anonymous.post(LOGIN, BAD, HTTP_X_FORWARDED_FOR="198.51.100.9, 203.0.113.1")
    elsewhere = anonymous.post(LOGIN, GOOD, HTTP_X_FORWARDED_FOR="198.51.100.9, 203.0.113.2")
    assert elsewhere.status_code == 200


def test_sign_out_closes_the_session(api: APIClient) -> None:
    assert api.post(f"{BASE}/logout/").status_code == 204
    assert api.get(ME).status_code == 403


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "me/"),
        ("post", "logout/"),
        ("post", "password/"),
        ("post", "username/"),
        ("put", "language/"),
    ],
)
def test_everything_but_setup_and_sign_in_needs_a_session(
    anonymous: APIClient, method: str, path: str
) -> None:
    assert getattr(anonymous, method)(f"{BASE}/{path}", {}).status_code == 403


def test_me_counts_failures_since_the_last_sign_in(anonymous: APIClient, owner: User) -> None:
    for _ in range(2):
        anonymous.post(LOGIN, BAD)
    anonymous.post(LOGIN, GOOD)
    assert anonymous.get(ME).json()["failed_attempts"] == 0
    anonymous.post(LOGIN, BAD)
    assert anonymous.get(ME).json()["failed_attempts"] == 1


def test_password_change_keeps_the_session_and_retires_the_old_password(
    api: APIClient, owner: User
) -> None:
    body = {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    assert api.post(f"{BASE}/password/", body).status_code == 204
    assert api.get(ME).status_code == 200
    owner.refresh_from_db()
    assert owner.check_password(NEW_PASSWORD) and not owner.check_password(PASSWORD)


@pytest.mark.parametrize(
    "body",
    [
        {"current_password": "wrong", "new_password": NEW_PASSWORD},
        {"current_password": PASSWORD, "new_password": "1234"},
        # Too close to the username.
        {"current_password": PASSWORD, "new_password": "owner123"},
    ],
)
def test_password_change_is_refused(api: APIClient, owner: User, body: dict[str, str]) -> None:
    assert api.post(f"{BASE}/password/", body).status_code == 400
    owner.refresh_from_db()
    assert owner.check_password(PASSWORD)


def test_wrong_current_password_says_so(api: APIClient) -> None:
    response = api.post(f"{BASE}/username/", {"current_password": "wrong", "username": "new"})
    assert response.json()["current_password"] == ["The current password is not correct."]


@pytest.mark.parametrize("endpoint", ["password", "username"])
def test_guessing_the_current_password_locks_out_like_sign_in_does(
    api: APIClient, endpoint: str
) -> None:
    # A hijacked session must not allow unlimited guesses.
    body = {"new_password": NEW_PASSWORD, "username": "renamed"}
    for _ in range(5):
        api.post(f"{BASE}/{endpoint}/", {**body, "current_password": "wrong"})
    response = api.post(f"{BASE}/{endpoint}/", {**body, "current_password": PASSWORD})
    assert response.status_code == 429


def test_username_change(api: APIClient, owner: User) -> None:
    response = api.post(f"{BASE}/username/", {"current_password": PASSWORD, "username": "javi"})
    assert response.status_code == 200
    assert response.json() == {"username": "javi", "language": ""}
    owner.refresh_from_db()
    assert owner.username == "javi"


@pytest.mark.parametrize("username", ["", "not valid!", "x" * 151])
def test_username_change_applies_django_rules(api: APIClient, owner: User, username: str) -> None:
    body = {"current_password": PASSWORD, "username": username}
    assert api.post(f"{BASE}/username/", body).status_code == 400
    owner.refresh_from_db()
    assert owner.username == "owner"


def test_language_is_stored_and_returned_with_the_profile(api: APIClient) -> None:
    assert api.get(ME).json()["language"] == ""
    assert api.put(f"{BASE}/language/", {"language": "es"}).json() == {"language": "es"}
    assert api.get(ME).json()["language"] == "es"
    assert api.put(f"{BASE}/language/", {"language": "en"}).status_code == 200
    assert Profile.objects.get().language == "en"


def test_language_must_be_one_the_application_has(api: APIClient) -> None:
    assert api.put(f"{BASE}/language/", {"language": "fr"}).status_code == 400


def test_profile_text(owner: User) -> None:
    assert str(Profile(user=owner, language="es")) == f"{owner.pk}:es"
    assert str(Profile(user=owner)) == f"{owner.pk}:-"


def test_signing_in_and_out_is_logged(anonymous: APIClient, owner: User) -> None:
    anonymous.post(LOGIN, GOOD)
    anonymous.post(f"{BASE}/logout/")
    actions = ActivityLog.objects.filter(username="owner").values_list("action", flat=True)
    assert sorted(actions) == ["auth.login", "auth.logout"]


def test_failed_sign_in_is_logged_without_the_password(anonymous: APIClient, owner: User) -> None:
    anonymous.post(LOGIN, {"username": "owner", "password": "a-secret-guess"})
    entry = ActivityLog.objects.get(action="auth.login_failed")
    assert entry.user is None
    assert entry.detail == {"username": "owner"}


def test_session_expires_after_inactivity_and_activity_renews_it(
    anonymous: APIClient, owner: User
) -> None:
    anonymous.post(LOGIN, GOOD)
    session = Session.objects.get()
    session.expire_date = timezone.now() + timedelta(seconds=10)
    session.save()

    anonymous.get(ME)
    session.refresh_from_db()
    assert (session.expire_date - timezone.now()).total_seconds() > 10 * 60

    session.expire_date = timezone.now() - timedelta(seconds=1)
    session.save()
    assert anonymous.get(ME).status_code == 403


def test_background_polling_does_not_renew_the_session(anonymous: APIClient, owner: User) -> None:
    anonymous.post(LOGIN, GOOD)
    session = Session.objects.get()
    soon = timezone.now() + timedelta(seconds=10)
    session.expire_date = soon
    session.save()

    assert anonymous.get(ME, headers={"X-Background-Poll": "1"}).status_code == 200
    session.refresh_from_db()
    assert session.expire_date == soon

    anonymous.get(ME)
    session.refresh_from_db()
    assert session.expire_date > soon + timedelta(minutes=10)
