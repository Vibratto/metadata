"""Proxy choice by each service's IPv4/IPv6 support. DNS is faked: a service
"has" a family when it resolves to an address of that family.
"""

import socket
from typing import Any

import pytest
import requests
import responses

from proxies.models import Proxy
from proxies.routing import NoCompatibleProxy, ProxyRouter, proxied_session

pytestmark = pytest.mark.django_db

V4 = "http://v4:3128"
V6 = "http://v6:3128"


@pytest.fixture
def proxies() -> None:
    Proxy.objects.create(url=V4, ip_version=Proxy.IpVersion.IPV4)
    Proxy.objects.create(url=V6, ip_version=Proxy.IpVersion.IPV6)


def _chosen(url: str, times: int = 4) -> set[str | None]:
    router = ProxyRouter()
    return {router.acquire(url) for _ in range(times)}


def test_new_proxies_are_ipv4_by_default() -> None:
    assert Proxy.objects.create(url=V4).ip_version == Proxy.IpVersion.IPV4


@pytest.mark.usefixtures("proxies")
def test_ipv4_only_service_uses_only_ipv4_proxies(dns: Any) -> None:
    dns("music.youtube.com", socket.AF_INET)
    assert _chosen("https://music.youtube.com/browse/1") == {V4}


@pytest.mark.usefixtures("proxies")
def test_ipv6_only_service_uses_only_ipv6_proxies(dns: Any) -> None:
    dns("v6.example.test", socket.AF_INET6)
    assert _chosen("https://v6.example.test/x") == {V6}


@pytest.mark.usefixtures("proxies")
def test_dual_stack_service_uses_every_proxy(dns: Any) -> None:
    dns("lrclib.net", socket.AF_INET, socket.AF_INET6)
    assert _chosen("https://lrclib.net/api/get") == {V4, V6}


@pytest.mark.usefixtures("proxies")
def test_support_is_checked_only_the_first_time(dns: Any) -> None:
    lookups = dns("music.youtube.com", socket.AF_INET)
    _chosen("https://music.youtube.com/a")
    first = len(lookups)
    assert first > 0
    # Another router (another job, another process) no longer asks the DNS.
    _chosen("https://music.youtube.com/b")
    _chosen("http://music.youtube.com/c")
    assert len(lookups) == first


@pytest.mark.usefixtures("proxies")
def test_each_service_is_checked_on_its_own(dns: Any) -> None:
    dns("music.youtube.com", socket.AF_INET)
    dns("v6.example.test", socket.AF_INET6)
    assert _chosen("https://music.youtube.com/a") == {V4}
    assert _chosen("https://v6.example.test/a") == {V6}


@pytest.mark.usefixtures("proxies")
def test_unresolvable_service_is_checked_again_next_time(dns: Any) -> None:
    lookups = dns("down.example.test")
    # No DNS answer drops no proxy.
    assert _chosen("https://down.example.test/a") == {V4, V6}
    first = len(lookups)
    dns("down.example.test", socket.AF_INET)
    assert _chosen("https://down.example.test/a") == {V4}
    assert len(lookups) > first


def test_no_compatible_proxy_fails_instead_of_connecting_directly(dns: Any) -> None:
    Proxy.objects.create(url=V6, ip_version=Proxy.IpVersion.IPV6)
    dns("music.youtube.com", socket.AF_INET)
    with pytest.raises(NoCompatibleProxy, match="music.youtube.com"):
        ProxyRouter().acquire("https://music.youtube.com/a")


@responses.activate
def test_proxied_session_never_falls_back_to_a_direct_connection(dns: Any) -> None:
    Proxy.objects.create(url=V6, ip_version=Proxy.IpVersion.IPV6)
    dns("music.youtube.com", socket.AF_INET)
    responses.get("https://music.youtube.com/infos", json={})
    with pytest.raises(requests.ConnectionError):
        proxied_session().get("https://music.youtube.com/infos")
    assert len(responses.calls) == 0


def test_without_proxies_connection_is_direct(dns: Any) -> None:
    dns("music.youtube.com", socket.AF_INET)
    assert _chosen("https://music.youtube.com/a") == {None}


def test_disabled_proxies_are_not_used(dns: Any) -> None:
    Proxy.objects.create(url=V4, enabled=False)
    dns("music.youtube.com", socket.AF_INET)
    assert _chosen("https://music.youtube.com/a") == {None}


def test_failed_proxy_is_sidelined_and_counted(dns: Any) -> None:
    other = "http://other:3128"
    Proxy.objects.create(url=V4)
    Proxy.objects.create(url=other)
    dns("music.youtube.com", socket.AF_INET)
    router = ProxyRouter()
    failed = router.acquire("https://music.youtube.com/a")
    assert failed is not None
    router.report(failed, ok=False)
    assert {router.acquire("https://music.youtube.com/a") for _ in range(3)} == {
        {V4, other}.difference({failed}).pop()
    }
    assert Proxy.objects.get(url=failed).failure_count == 1


def test_success_is_counted(dns: Any) -> None:
    Proxy.objects.create(url=V4)
    dns("music.youtube.com", socket.AF_INET)
    router = ProxyRouter()
    router.report(router.acquire("https://music.youtube.com/a") or "", ok=True)
    proxy = Proxy.objects.get(url=V4)
    assert proxy.success_count == 1
    assert proxy.last_used_at is not None


def test_every_proxy_cooling_down_is_a_connection_error(dns: Any) -> None:
    Proxy.objects.create(url=V4)
    dns("music.youtube.com", socket.AF_INET)
    router = ProxyRouter()
    router.report(router.acquire("https://music.youtube.com/a") or "", ok=False)
    with pytest.raises(requests.ConnectionError):
        router.acquire("https://music.youtube.com/a")


@responses.activate
def test_proxied_session_sends_through_a_compatible_proxy(dns: Any) -> None:
    Proxy.objects.create(url=V4)
    Proxy.objects.create(url=V6, ip_version=Proxy.IpVersion.IPV6)
    dns("music.youtube.com", socket.AF_INET)
    responses.get("https://music.youtube.com/infos", json={})
    proxied_session().get("https://music.youtube.com/infos")
    sent = getattr(responses.calls[0].request, "req_kwargs")["proxies"]  # noqa: B009
    assert sent["https"] == V4
    assert Proxy.objects.get(url=V4).success_count == 1


@responses.activate
def test_proxied_session_reports_connection_failures(dns: Any) -> None:
    Proxy.objects.create(url=V4)
    dns("music.youtube.com", socket.AF_INET)
    responses.get("https://music.youtube.com/infos", body=requests.ConnectionError("refused"))
    with pytest.raises(requests.ConnectionError):
        proxied_session().get("https://music.youtube.com/infos")
    assert Proxy.objects.get(url=V4).failure_count == 1
