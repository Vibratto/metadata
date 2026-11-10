"""Proxy API tests."""

import pytest
import requests
import responses
from rest_framework.test import APIClient

from activity.models import ActivityLog
from proxies.models import Proxy
from proxies.views import CHECK_URL

pytestmark = pytest.mark.django_db

URL = "/api/v1/proxies/"
PROXY = "http://127.0.0.1:8080"


@pytest.fixture
def proxy() -> Proxy:
    return Proxy.objects.create(url=PROXY)


def test_anonymous_is_forbidden() -> None:
    assert APIClient().get(URL).status_code == 403


def test_admin_creates_and_lists_proxies(api: APIClient) -> None:
    response = api.post(URL, {"url": PROXY}, format="json")
    assert response.status_code == 201
    assert api.get(URL).json()[0]["url"] == PROXY
    assert ActivityLog.objects.filter(
        action="proxies.created", username="owner", object_id=str(response.json()["id"])
    ).exists()


def test_counters_are_read_only(api: APIClient) -> None:
    response = api.post(URL, {"url": PROXY, "success_count": 99}, format="json")
    assert response.json()["success_count"] == 0


@pytest.mark.parametrize("url", ["ftp://host:21", "http://", "no-es-una-url"])
def test_rejects_invalid_urls(api: APIClient, url: str) -> None:
    assert api.post(URL, {"url": url}, format="json").status_code == 400


def test_admin_updates_and_deletes(api: APIClient, proxy: Proxy) -> None:
    response = api.patch(f"{URL}{proxy.pk}/", {"enabled": False}, format="json")
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert api.delete(f"{URL}{proxy.pk}/").status_code == 204
    assert not Proxy.objects.exists()
    for action in ("proxies.updated", "proxies.deleted"):
        assert ActivityLog.objects.filter(
            action=action, username="owner", object_id=str(proxy.pk)
        ).exists()


@responses.activate
def test_check_reports_success(api: APIClient, proxy: Proxy) -> None:
    responses.get(CHECK_URL, status=200)
    response = api.post(f"{URL}{proxy.pk}/check/")
    assert response.json() == {"ok": True, "status_code": 200}
    assert ActivityLog.objects.filter(action="proxies.checked").exists()


@responses.activate
def test_check_reports_an_error_status(api: APIClient, proxy: Proxy) -> None:
    responses.get(CHECK_URL, status=403)
    response = api.post(f"{URL}{proxy.pk}/check/")
    assert response.json() == {"ok": False, "status_code": 403}


@responses.activate
def test_check_hides_connection_errors(api: APIClient, proxy: Proxy) -> None:
    # The error text may carry the proxy URL with credentials: it is never returned.
    responses.get(CHECK_URL, body=requests.ConnectionError(f"{PROXY} refused"))
    response = api.post(f"{URL}{proxy.pk}/check/")
    assert response.json() == {"ok": False, "status_code": None}
    assert PROXY not in response.content.decode()


def test_check_unknown_proxy_is_404(api: APIClient) -> None:
    assert api.post(f"{URL}999/check/").status_code == 404


def test_admin_sets_the_ip_version(api: APIClient) -> None:
    response = api.post(URL, {"url": PROXY, "ip_version": "ipv6"}, format="json")
    assert response.status_code == 201
    assert response.json()["ip_version"] == "ipv6"
    assert Proxy.objects.get(url=PROXY).ip_version == Proxy.IpVersion.IPV6


def test_ip_version_defaults_to_ipv4(api: APIClient) -> None:
    assert api.post(URL, {"url": PROXY}, format="json").json()["ip_version"] == "ipv4"


def test_unknown_ip_version_is_rejected(api: APIClient) -> None:
    assert api.post(URL, {"url": PROXY, "ip_version": "ipv5"}, format="json").status_code == 400
