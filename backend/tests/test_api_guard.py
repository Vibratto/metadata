"""The API serves the application's own frontend and nothing else.

A request to ``/api/`` needs the ``X-Vibratto-Client: web`` header, and a browser that
says the request comes from another site is refused even with it. The health check stays
open for deployments, and frontend pages are unaffected.
"""

from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.test import Client

pytestmark = pytest.mark.django_db

PROTECTED = "/api/v1/preferences/"
FRONTEND = {"X-Vibratto-Client": "web"}


@pytest.fixture(autouse=True)
def guarded(settings: Any, client: Client, owner: User) -> None:
    """Turn the restriction on and sign in, so a 403 can only come from the guard."""
    settings.API_FRONTEND_ONLY = True
    client.force_login(owner)


def test_request_without_the_frontend_header_is_refused(client: Client) -> None:
    response = client.get(PROTECTED)
    assert response.status_code == 403
    assert response.json() == {"detail": "This API can only be used by the application's frontend."}


def test_request_with_the_frontend_header_is_served(client: Client) -> None:
    assert client.get(PROTECTED, headers=FRONTEND).status_code == 200


def test_header_must_carry_the_frontend_value(client: Client) -> None:
    assert client.get(PROTECTED, headers={"X-Vibratto-Client": "other"}).status_code == 403


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_another_website_is_refused_even_with_the_header(client: Client, site: str) -> None:
    response = client.get(PROTECTED, headers={**FRONTEND, "Sec-Fetch-Site": site})
    assert response.status_code == 403


@pytest.mark.parametrize("site", ["same-origin", "none"])
def test_own_origin_is_served(client: Client, site: str) -> None:
    response = client.get(PROTECTED, headers={**FRONTEND, "Sec-Fetch-Site": site})
    assert response.status_code == 200


def test_writes_need_the_header_too(client: Client) -> None:
    response = client.post("/api/v1/proxies/", {}, content_type="application/json")
    assert response.status_code == 403


def test_health_check_stays_open(client: Client) -> None:
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_frontend_pages_are_not_affected(client: Client, settings: Any, tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<div id=app></div>")
    settings.FRONTEND_DIST = tmp_path
    assert client.get("/library").status_code == 200


def test_restriction_can_be_turned_off(client: Client, settings: Any) -> None:
    settings.API_FRONTEND_ONLY = False
    assert client.get(PROTECTED).status_code == 200


def test_refusal_is_translated(client: Client) -> None:
    response = client.get(PROTECTED, headers={"Accept-Language": "es"})
    assert response.status_code == 403
    assert response.json() == {
        "detail": "Esta API solo la puede usar el frontend de la aplicación."
    }
