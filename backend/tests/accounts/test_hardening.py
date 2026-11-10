"""HTTP hardening: security headers, cookies and Django's deployment checks."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client
from rest_framework.test import APIClient

from tests.conftest import PASSWORD, USERNAME

BACKEND = Path(__file__).resolve().parents[2]


def _directive(header: str, name: str) -> list[str]:
    directives = {d.split()[0]: d.split()[1:] for d in header.split(";") if d.strip()}
    return directives[name]


def test_content_security_policy_allows_no_inline_or_evaluated_scripts(client: Client) -> None:
    scripts = _directive(client.get("/api/health/")["Content-Security-Policy"], "script-src")
    assert scripts == ["'self'"]


def test_frames_are_denied_and_hsts_is_sent_over_https_only(client: Client) -> None:
    response = client.get("/api/health/", secure=True)
    assert response["X-Frame-Options"] == "DENY"
    assert "max-age=" in response["Strict-Transport-Security"]
    assert "Strict-Transport-Security" not in client.get("/api/health/")


@pytest.mark.django_db
def test_session_cookie_is_http_only_secure_and_expires(owner: User) -> None:
    response = APIClient().post(
        "/api/v1/accounts/login/", {"username": USERNAME, "password": PASSWORD}
    )
    cookie = response.cookies[settings.SESSION_COOKIE_NAME]
    assert cookie["httponly"] and cookie["secure"]
    assert cookie["samesite"] == "Lax"
    assert cookie["max-age"] == settings.SESSION_COOKIE_AGE


def test_production_settings_pass_the_deployment_checks() -> None:
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.base",
        "DJANGO_SECRET_KEY": "x7#k9Qz" * 10,
        "DJANGO_ALLOWED_HOSTS": "music.example.org",
    }
    command = [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"]
    result = subprocess.run(  # noqa: S603
        command, cwd=BACKEND, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
