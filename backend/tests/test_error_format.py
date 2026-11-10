"""Every API error carries a ``detail`` text."""

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_validation_error_has_detail_and_keeps_the_field_errors(api: APIClient) -> None:
    response = api.post("/api/v1/proxies/", {"url": "not-a-url"}, format="json")
    assert response.status_code == 400
    assert isinstance(response.json()["detail"], str) and response.json()["detail"]
    assert isinstance(response.json()["url"], list)


def test_not_found_has_detail(api: APIClient) -> None:
    response = api.get("/api/v1/preferences/does-not-exist/")
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)


def test_missing_session_has_detail(anonymous: APIClient) -> None:
    response = anonymous.get("/api/v1/proxies/")
    assert response.status_code == 403
    assert isinstance(response.json()["detail"], str)
