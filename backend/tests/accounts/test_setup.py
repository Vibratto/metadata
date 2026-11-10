"""Creation of the application's single account."""

from typing import Any

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from tests.conftest import PASSWORD

pytestmark = pytest.mark.django_db

SETUP = "/api/v1/accounts/setup/"
ME = "/api/v1/accounts/me/"
CODE = "one-time-c0de"


def test_setup_is_needed_while_no_account_exists(anonymous: APIClient) -> None:
    response = anonymous.get(SETUP)
    assert response.json() == {"needed": True, "code_required": False}
    # The sign-in form needs this cookie before it can post.
    assert "csrftoken" in response.cookies


def test_setup_is_closed_once_the_account_exists(anonymous: APIClient, owner: User) -> None:
    assert anonymous.get(SETUP).json() == {"needed": False, "code_required": False}


def test_setup_creates_the_account_and_signs_it_in(anonymous: APIClient) -> None:
    response = anonymous.post(SETUP, {"username": "root", "password": PASSWORD})
    assert response.status_code == 201
    assert response.json() == {"username": "root", "language": ""}
    user = User.objects.get()
    assert user.is_superuser and user.check_password(PASSWORD)
    assert anonymous.get(ME).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"username": "root", "password": "1234"},
        {"username": "root", "password": "12345678901"},
        {"username": "not a valid name!", "password": PASSWORD},
        {"username": "root"},
    ],
)
def test_setup_applies_django_username_and_password_rules(
    anonymous: APIClient, body: dict[str, str]
) -> None:
    assert anonymous.post(SETUP, body).status_code == 400
    assert not User.objects.exists()


def test_setup_cannot_create_a_second_account(anonymous: APIClient, owner: User) -> None:
    response = anonymous.post(SETUP, {"username": "intruder", "password": PASSWORD})
    assert response.status_code == 403
    assert list(User.objects.values_list("username", flat=True)) == ["owner"]


def test_setup_enforces_csrf() -> None:
    client = APIClient(enforce_csrf_checks=True)
    assert client.post(SETUP, {"username": "root", "password": PASSWORD}).status_code == 403
    assert not User.objects.exists()


@pytest.fixture
def with_code(settings: Any) -> None:
    settings.VIBRATTO_SETUP_CODE = CODE


@pytest.mark.usefixtures("with_code")
def test_status_says_when_a_code_is_required(anonymous: APIClient) -> None:
    assert anonymous.get(SETUP).json() == {"needed": True, "code_required": True}


@pytest.mark.usefixtures("with_code")
@pytest.mark.parametrize("code", [None, "", "another-code", CODE.upper(), CODE[:-1]])
def test_nothing_is_created_without_the_exact_code(anonymous: APIClient, code: str | None) -> None:
    body = {"username": "root", "password": PASSWORD}
    if code is not None:
        body["code"] = code
    response = anonymous.post(SETUP, body)
    assert response.status_code == 403
    assert response.json()["detail"] == "The setup code is not correct."
    assert not User.objects.exists()


@pytest.mark.usefixtures("with_code")
def test_the_right_code_creates_the_account(anonymous: APIClient) -> None:
    body = {"username": "root", "password": PASSWORD, "code": CODE}
    assert anonymous.post(SETUP, body).status_code == 201
    assert User.objects.filter(username="root").exists()
