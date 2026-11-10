"""Spacing between requests to services that ask clients to slow down."""

import threading
import time
from collections.abc import Callable


class RateLimiter:
    """Keeps calls at least ``interval`` seconds apart, across threads too.

    The lock is held while waiting, so concurrent callers queue up. The clock and the
    sleep function can be replaced so tests do not wait.
    """

    def __init__(
        self,
        interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        """Block until the next call is allowed."""
        with self._lock:
            if self._last is not None:
                remaining = self._last + self._interval - self._clock()
                if remaining > 0:
                    self._sleep(remaining)
            self._last = self._clock()
