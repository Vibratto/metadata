"""Per-request proxy choice by the service's IPv4/IPv6 support. A proxy only
reaches services of its own address family, so the first time a host is used its
DNS records (A and AAAA) are checked and stored in ``ServiceIpSupport``; from then
on the stored answer decides which proxies are eligible, without another lookup.
"""

import time
from socket import AF_INET, AF_INET6, gaierror, getaddrinfo
from urllib.parse import urlsplit

import requests
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext as _

from integrations.http import build_session
from integrations.youtube import NoProxyAvailable, ProxyPool

from .models import Proxy, ServiceIpSupport


def _resolves(host: str, family: int) -> bool:
    """Whether the host has one."""
    try:
        return bool(getaddrinfo(host, 443, family))
    except (gaierror, OSError):
        return False


def _versions(host: str) -> set[str] | None:
    """The service's IP versions, checked only the first time.

    Returns:
        Supported versions, or ``None``
        when DNS gave no answer: nothing is stored and the next use tries again.
    """
    support = ServiceIpSupport.objects.filter(host=host).first()
    if support is None:
        ipv4, ipv6 = _resolves(host, AF_INET), _resolves(host, AF_INET6)
        if not (ipv4 or ipv6):
            return None
        # Two tasks may check the same host at once; the first row wins.
        support, _created = ServiceIpSupport.objects.get_or_create(
            host=host, defaults={"ipv4": ipv4, "ipv6": ipv6}
        )
    return {
        version
        for version, ok in (
            (Proxy.IpVersion.IPV4, support.ipv4),
            (Proxy.IpVersion.IPV6, support.ipv6),
        )
        if ok
    }


class NoCompatibleProxy(requests.exceptions.ProxyError):
    """Proxies are enabled, but none has an IP version the service supports. Connecting
    directly would reveal the address the proxies are there to hide.
    """


def build_pool(url: str) -> ProxyPool:
    """Pool of the enabled proxies that can reach the service behind ``url``. Without
    enabled proxies the pool is empty and the connection is direct.

    Raises:
        NoCompatibleProxy: Proxies are enabled but none can reach the service.
    """
    proxies = Proxy.objects.filter(enabled=True)
    # Without proxies there is nothing to check.
    if not proxies.exists():
        return ProxyPool([])
    host = urlsplit(url).hostname or ""
    versions = _versions(host)
    if versions is not None:
        proxies = proxies.filter(ip_version__in=versions)
    urls = list(proxies.values_list("url", flat=True))
    if not urls:
        raise NoCompatibleProxy(
            _("No enabled proxy supports the IP version of %(host)s.") % {"host": host}
        )
    return ProxyPool(urls)


def record_use(url: str | None, *, ok: bool) -> None:
    """Updates the used proxy's counters."""
    if url is None:
        return
    now = timezone.now()
    if ok:
        Proxy.objects.filter(url=url).update(success_count=F("success_count") + 1, last_used_at=now)
    else:
        Proxy.objects.filter(url=url).update(
            failure_count=F("failure_count") + 1, last_used_at=now, last_failed_at=now
        )


class ProxyRouter:
    """Hands out proxies per service and sidelines the ones that fail. One pool per
    host, built on first use, so each service only sees compatible proxies. Not
    thread-safe: each task or request builds its own router.
    """

    def __init__(self) -> None:
        """Creates the router with no pools yet."""
        self._pools: dict[str, ProxyPool] = {}

    def _pool(self, host: str) -> ProxyPool:
        if host not in self._pools:
            self._pools[host] = build_pool(f"//{host}")
        return self._pools[host]

    def acquire(self, url: str) -> str | None:
        """Proxy for the request to ``url``, or ``None`` for a direct connection.

        Raises:
            requests.ConnectionError: If every compatible proxy is cooling down, or
                none is compatible; callers already handle network errors.
        """
        try:
            return self._pool(urlsplit(url).hostname or "").acquire(time.monotonic())
        except NoProxyAvailable as error:
            raise requests.exceptions.ProxyError(str(error)) from error

    def report(self, proxy: str, *, ok: bool) -> None:
        """Records the proxy's outcome in its pools and in its counters."""
        for pool in self._pools.values():
            if ok:
                pool.report_success(proxy)
            else:
                pool.report_failure(proxy, time.monotonic())
        record_use(proxy, ok=ok)


def proxied_session() -> requests.Session:
    """Shared HTTP session that goes out through the proxies each service supports."""
    return build_session(router=ProxyRouter())
