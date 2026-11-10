"""Tests for the shared HTTP client."""

from typing import Any

import pytest
import responses
from requests.adapters import HTTPAdapter
from urllib3 import HTTPResponse

from integrations.http import DEFAULT_TIMEOUT, USER_AGENT, build_session


def _timeout_sent() -> Any:
    """Timeout of the last request."""
    return getattr(responses.calls[-1].request, "req_kwargs")["timeout"]  # noqa: B009


@responses.activate
def test_sends_project_user_agent() -> None:
    responses.get("https://api.example.test/x", json={})
    build_session().get("https://api.example.test/x")
    assert responses.calls[0].request.headers["User-Agent"] == USER_AGENT


@responses.activate
def test_custom_user_agent() -> None:
    responses.get("https://api.example.test/x", json={})
    build_session(user_agent="Otro/1.0").get("https://api.example.test/x")
    assert responses.calls[0].request.headers["User-Agent"] == "Otro/1.0"


@responses.activate
def test_applies_default_timeout() -> None:
    responses.get("https://api.example.test/x", json={})
    build_session().get("https://api.example.test/x")
    assert _timeout_sent() == DEFAULT_TIMEOUT


@responses.activate
def test_explicit_timeout_wins() -> None:
    responses.get("https://api.example.test/x", json={})
    build_session().get("https://api.example.test/x", timeout=2)
    assert _timeout_sent() == 2


def test_retries_only_idempotent_methods_on_transient_errors() -> None:
    adapter = build_session().get_adapter("https://api.example.test")
    assert isinstance(adapter, HTTPAdapter)
    retry = adapter.max_retries
    assert retry.total == 3
    assert 503 in retry.status_forcelist
    assert retry.allowed_methods == ("GET", "HEAD")


@responses.activate
def test_forwards_tls_and_proxy_options(monkeypatch: pytest.MonkeyPatch) -> None:
    """The adapter passes everything else through: losing ``verify`` would turn TLS checks off."""
    for name in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        monkeypatch.delenv(name, raising=False)
    responses.get("https://api.example.test/x", json={})
    session = build_session()
    session.get("https://api.example.test/x")
    assert getattr(responses.calls[-1].request, "req_kwargs")["verify"] is True  # noqa: B009

    proxies = {"https": "http://proxy.test:3128"}
    session.get(
        "https://api.example.test/x", stream=True, verify="/ca.pem", cert="c.pem", proxies=proxies
    )
    sent = getattr(responses.calls[-1].request, "req_kwargs")  # noqa: B009
    assert (sent["stream"], sent["verify"], sent["cert"]) == (True, "/ca.pem", "c.pem")
    assert sent["proxies"]["https"] == "http://proxy.test:3128"


def test_waits_retry_after_plus_up_to_thirty_percent() -> None:
    """On a 429 the ``Retry-After`` wait is honoured, plus up to 30 % at random, so
    several workers told to wait do not all come back at the same instant.
    """
    adapter = build_session().get_adapter("https://api.example.test")
    assert isinstance(adapter, HTTPAdapter)
    response = HTTPResponse(status=429, headers={"Retry-After": "10"})
    waits = {adapter.max_retries.get_retry_after(response) for _ in range(200)}
    assert all(w is not None and 10 <= w <= 13 for w in waits)
    assert len(waits) > 1


def test_no_retry_after_header_means_no_extra_wait() -> None:
    adapter = build_session().get_adapter("https://api.example.test")
    assert isinstance(adapter, HTTPAdapter)
    assert adapter.max_retries.get_retry_after(HTTPResponse(status=429)) is None
