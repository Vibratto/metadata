"""Proxy selection and rotation with a cool-down after failures. Pure logic: the
caller passes the proxy list and the current time, so there is no database,
clock or network access here.
"""


class NoProxyAvailable(Exception):  # noqa: N818
    """Every proxy is cooling down.

    Attributes:
        retry_in: Seconds until the first one is available again.
    """

    def __init__(self, retry_in: float) -> None:
        """Stores the remaining wait."""
        super().__init__(f"No proxy available for {retry_in:.0f}s")
        self.retry_in = retry_in


class ProxyPool:
    """Hands proxies out round-robin and sidelines the ones that fail. Each
    consecutive failure doubles the cool-down, up to ``max_cooldown``.
    """

    def __init__(
        self, urls: list[str], base_cooldown: float = 60.0, max_cooldown: float = 3600.0
    ) -> None:
        """Creates the pool.

        Args:
            base_cooldown: Wait after
                the first failure, in seconds.
            max_cooldown: Wait cap, in seconds.
        """
        self._urls = list(urls)
        self._base = base_cooldown
        self._max = max_cooldown
        self._failures: dict[str, int] = {}
        self._available_at: dict[str, float] = {}
        self._next = 0

    def acquire(self, now: float) -> str | None:
        """Returns the next available proxy.

        Args:
            now: Current time in seconds.

        Returns:
            Proxy URL, or ``None`` when the pool is empty (direct connection).

        Raises:
            NoProxyAvailable: If all are cooling down.
        """
        if not self._urls:
            return None
        for offset in range(len(self._urls)):
            index = (self._next + offset) % len(self._urls)
            url = self._urls[index]
            if self._available_at.get(url, 0.0) <= now:
                self._next = index + 1
                return url
        raise NoProxyAvailable(min(self._available_at[u] for u in self._urls) - now)

    def report_failure(self, url: str, now: float) -> None:
        """Sidelines the proxy with a growing wait."""
        failures = self._failures.get(url, 0) + 1
        self._failures[url] = failures
        cooldown = min(self._base * 2 ** (failures - 1), self._max)
        self._available_at[url] = now + cooldown

    def report_success(self, url: str) -> None:
        """Forgets the proxy's failures."""
        self._failures.pop(url, None)
        self._available_at.pop(url, None)
