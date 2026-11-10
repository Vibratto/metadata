"""Bulk proxy import tests (issue #222)."""

from typing import Any

import pytest
import responses
from rest_framework.test import APIClient

from activity.models import ActivityLog
from proxies.models import Proxy

pytestmark = pytest.mark.django_db

BULK = "/api/v1/proxies/bulk/"


def _bulk(client: APIClient, text: str, **extra: object) -> Any:
    return client.post(BULK, {"text": text, **extra}, format="json")


def test_each_supported_format_creates_a_proxy(api: APIClient) -> None:
    text = "\n".join(
        [
            "socks5://u:p@10.0.0.1:1080",
            "http://h1.example:8080",
            "h2.example:3128",
            "h3.example:9000:usuario:clave",
            "https://[2001:db8::1]:443",
        ]
    )
    response = _bulk(api, text)
    assert response.status_code == 200
    assert response.json()["created"] == 5
    assert set(Proxy.objects.values_list("url", flat=True)) == {
        "socks5://u:p@10.0.0.1:1080",
        "http://h1.example:8080",
        "http://h2.example:3128",
        "http://usuario:clave@h3.example:9000",
        "https://[2001:db8::1]:443",
    }


def test_default_scheme_applies_to_bare_host_and_port(api: APIClient) -> None:
    _bulk(api, "h.example:1080", default_scheme="socks5h")
    assert Proxy.objects.get().url == "socks5h://h.example:1080"


def test_ip_version_and_enabled_apply_to_every_line(api: APIClient) -> None:
    _bulk(api, "a.example:80\nb.example:81", ip_version="ipv6", enabled=False)
    proxies = list(Proxy.objects.all())
    assert len(proxies) == 2
    for proxy in proxies:
        assert proxy.ip_version == Proxy.IpVersion.IPV6
        assert proxy.enabled is False
        assert proxy.success_count == 0
        assert proxy.failure_count == 0


def test_defaults_are_ipv4_enabled_http(api: APIClient) -> None:
    _bulk(api, "a.example:80")
    proxy = Proxy.objects.get()
    assert proxy.url == "http://a.example:80"
    assert proxy.ip_version == Proxy.IpVersion.IPV4
    assert proxy.enabled is True


def test_blank_spaced_and_comment_lines_are_ignored(api: APIClient) -> None:
    response = _bulk(api, "\n   \n# comentario\n  http://a.example:80  \n")
    assert response.status_code == 200
    assert response.json()["created"] == 1
    assert response.json()["invalid"] == []
    assert Proxy.objects.get().url == "http://a.example:80"


def test_mixed_list_creates_valid_lines_and_reports_invalid_ones(api: APIClient) -> None:
    text = "\n".join(
        [
            "ftp://f.example:21",  # 1: esquema no permitido
            "http://:8080",  # 2: sin host
            "h.example",  # 3: sin puerto
            "h.example:70000",  # 4: puerto fuera de rango
            "http://ok.example:80",  # 5: valid
        ]
    )
    response = _bulk(api, text)
    body = response.json()
    assert response.status_code == 200
    assert body["created"] == 1
    assert [item["line"] for item in body["invalid"]] == [1, 2, 3, 4]
    assert all(item["reason"] for item in body["invalid"])
    assert Proxy.objects.get().url == "http://ok.example:80"


def test_list_without_valid_lines_is_400_and_creates_nothing(api: APIClient) -> None:
    response = _bulk(api, "ftp://x.example:21\nhttp://:80")
    assert response.status_code == 400
    assert [item["line"] for item in response.json()["invalid"]] == [1, 2]
    assert not Proxy.objects.exists()


def test_empty_text_is_400(api: APIClient) -> None:
    assert _bulk(api, "  \n# nada\n").status_code == 400
    assert not Proxy.objects.exists()


def test_duplicates_in_database_and_inside_the_list_are_reported(api: APIClient) -> None:
    Proxy.objects.create(url="http://a.example:80")
    text = "a.example:80\nhttp://a.example:80\nb.example:81\nb.example:81"
    body = _bulk(api, text, default_scheme="http").json()
    assert body["created"] == 1
    assert [item["line"] for item in body["duplicates"]] == [1, 2, 4]
    assert Proxy.objects.filter(url="http://a.example:80").count() == 1
    assert Proxy.objects.filter(url="http://b.example:81").count() == 1


def test_more_than_1000_lines_is_400(api: APIClient) -> None:
    text = "\n".join(f"h.example:{port}" for port in range(1, 1002))
    assert _bulk(api, text).status_code == 400
    assert not Proxy.objects.exists()


def test_1000_lines_are_accepted(api: APIClient) -> None:
    text = "\n".join(f"h.example:{port}" for port in range(1, 1001))
    assert _bulk(api, text).json()["created"] == 1000


def test_more_than_100_kb_is_400_and_creates_nothing(api: APIClient) -> None:
    comments = "\n".join("# " + "x" * 110 for _ in range(950))
    assert _bulk(api, comments + "\nhttp://a.example:80").status_code == 400
    assert not Proxy.objects.exists()


@pytest.mark.parametrize(
    "line",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "ftp://h.example:21",
        "http://h.example:80/ruta",
        "http://h.example:80?x=1",
        "http://h.example:80#fragmento",
        "http://h.example:80\x07",
    ],
)
def test_unsafe_lines_are_rejected(api: APIClient, line: str) -> None:
    response = _bulk(api, line)
    assert response.status_code == 400
    assert len(response.json()["invalid"]) == 1
    assert not Proxy.objects.exists()


def test_url_longer_than_500_characters_is_invalid(api: APIClient) -> None:
    long_line = "http://" + "a" * 495 + ".example:80"
    body = _bulk(api, f"{long_line}\nhttp://ok.example:80").json()
    assert body["created"] == 1
    assert [item["line"] for item in body["invalid"]] == [1]


def test_unknown_default_scheme_is_400(api: APIClient) -> None:
    assert _bulk(api, "a.example:80", default_scheme="ftp").status_code == 400


def test_anonymous_is_refused() -> None:
    assert _bulk(APIClient(), "a.example:80").status_code in (401, 403)
    assert not Proxy.objects.exists()


def test_credentials_never_appear_in_response_or_activity_log(api: APIClient) -> None:
    text = "\n".join(
        [
            "http://usuario-secreto:clave-secreta@ok.example:80",
            "http://otro:clave-invalida@x.example:99999",
            "ftp://ftp-user:clave-ftp@y.example:21",
        ]
    )
    response = _bulk(api, text)
    assert response.status_code == 200
    assert response.json()["created"] == 1
    for secret in ("usuario-secreto", "clave-secreta", "clave-invalida", "clave-ftp"):
        assert secret not in response.content.decode()
        assert secret not in "".join(str(vars(row)) for row in ActivityLog.objects.all())


@responses.activate
def test_bulk_import_makes_no_http_request(api: APIClient) -> None:
    _bulk(api, "a.example:80\nhttp://b.example:81")
    assert len(responses.calls) == 0
    assert Proxy.objects.count() == 2


def test_writes_a_single_activity_entry_with_counts(api: APIClient) -> None:
    Proxy.objects.create(url="http://a.example:80")
    _bulk(api, "a.example:80\nb.example:81\nftp://c.example:21")
    entries = ActivityLog.objects.filter(action="proxies.bulk_created")
    assert entries.count() == 1
    entry: Any = entries.get()
    detail: dict[str, Any] = entry.detail
    assert (detail["created"], detail["duplicates"], detail["invalid"]) == (1, 1, 1)
    assert not ActivityLog.objects.filter(action="proxies.created").exists()
    assert "b.example" not in str(detail)


@pytest.mark.parametrize(
    "line",
    [
        "http://[2001:db8::1:8080",  # IPv6 sin cerrar el corchete
        "http://[2001:db8::1]",  # IPv6 sin puerto
        "http://usuario@h.example:80",  # usuario sin clave
        "http://:clave@h.example:80",  # clave sin usuario
        "h.example:80:user:",  # empty password
        "h.example:80:usuario",  # falta la clave
        "http://u:p@h.example:80:x:y",  # credenciales en dos formatos a la vez
        "h.example:",  # empty port
    ],
)
def test_malformed_lines_are_rejected(api: APIClient, line: str) -> None:
    response = _bulk(api, line)
    assert response.status_code == 400
    assert [item["line"] for item in response.json()["invalid"]] == [1]
    assert not Proxy.objects.exists()


def test_proxy_created_by_a_concurrent_import_counts_as_duplicate(
    api: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Another import creates the same URL between the duplicate check and the insert: no error.
    Proxy.objects.create(url="http://a.example:80")
    monkeypatch.setattr(Proxy.objects, "filter", lambda *args, **kwargs: Proxy.objects.none())
    response = _bulk(api, "a.example:80")
    assert response.status_code == 200
    assert response.json() == {"created": 0, "duplicates": [{"line": 1}], "invalid": []}
    assert Proxy.objects.count() == 1
