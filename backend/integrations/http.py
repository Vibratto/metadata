"""Shared HTTP client for every integration."""

import random
from collections.abc import Mapping
from typing import Any, Protocol

import requests
from requests.adapters import HTTPAdapter
from urllib3 import BaseHTTPResponse
from urllib3.util import Retry

USER_AGENT = "VibrattoMetadata/0.1 (+https://github.com/Vibratto/metadata)"
DEFAULT_TIMEOUT = 10.0

#: Maximum extra added to ``Retry-After``.
RETRY_AFTER_JITTER = 0.3


class _JitteredRetry(Retry):
    """Retries that wait ``Retry-After`` plus up to 30 % at random, so workers told
    to wait the same time do not all return at once (LRCLIB asks for it).
    """

    def get_retry_after(self, response: BaseHTTPResponse) -> float | None:
        """The service's wait, jittered."""
        seconds = super().get_retry_after(response)
        if seconds is None:
            return None
        return seconds * random.uniform(1, 1 + RETRY_AFTER_JITTER)  # noqa: S311  # not cryptography


_RETRY = _JitteredRetry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    # Idempotent methods only: retrying a POST could repeat its side effect.
    allowed_methods=("GET", "HEAD"),
)


class ProxyRouter(Protocol):
    """Picks the proxy for each request and is told how it went."""

    def acquire(self, url: str) -> str | None:
        """Proxy for ``url``, or direct."""

    def report(self, proxy: str, *, ok: bool) -> None:
        """Records whether the proxy answered."""


class _TimeoutAdapter(HTTPAdapter):
    """Adapter that applies a timeout when the call does not set one. ``requests``
    has no session-wide timeout, and a missing one can hang a worker forever.
    With a router, each request also goes out through the proxy it picks.
    """

    def __init__(self, timeout: float, router: ProxyRouter | None = None, **kwargs: Any) -> None:
        """Stores the timeout and the router."""
        self._timeout = timeout
        self._router = router
        super().__init__(**kwargs)

    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: None | float | tuple[float, float] | tuple[float, None] = None,
        verify: bool | str = True,
        cert: None | bytes | str | tuple[bytes | str, bytes | str] = None,
        proxies: Mapping[str, str] | None = None,
    ) -> requests.Response:
        """Sends the request with a timeout."""
        if timeout is None:
            timeout = self._timeout
        router = self._router
        proxy = router.acquire(request.url or "") if router else None
        if router is None or proxy is None:
            return super().send(request, stream, timeout, verify, cert, proxies)
        try:
            response = super().send(
                request, stream, timeout, verify, cert, {"http": proxy, "https": proxy}
            )
        except requests.ConnectionError:
            # Only network failures count against the proxy; a 4xx/5xx is the service's.
            router.report(proxy, ok=False)
            raise
        router.report(proxy, ok=True)
        return response


def build_session(
    user_agent: str = USER_AGENT,
    timeout: float = DEFAULT_TIMEOUT,
    router: ProxyRouter | None = None,
) -> requests.Session:
    """Builds a session with a timeout, retries and the project's ``User-Agent``.

    Args:
        user_agent: Cabecera ``User-Agent`` a enviar. / ``User-Agent`` header to send.
        timeout: Seconds to wait per request.
        router: Picks each request's proxy; without one, a direct connection.

    Returns:
        Session ready for ``http://`` and ``https://``.
    """
    session = requests.Session()
    session.headers["User-Agent"] = user_agent
    adapter = _TimeoutAdapter(timeout, router, max_retries=_RETRY)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
