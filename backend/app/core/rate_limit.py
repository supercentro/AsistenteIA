"""In-memory rate limiting for the unauthenticated entry points (login and registration).

Limitations (see docs/development_guide.md): counters live in the process memory, are lost on
restart and are not shared between workers or instances. The key is the connection peer address;
forwarding headers supplied by clients are never read here.
"""

import math
import time

from limits import RateLimitItem
from limits import parse as parse_rate_limit
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from app.core.errors import RateLimitedError


class RateLimiter:
    """One limit per client address; each instance has its own counters (namespace)."""

    def __init__(self, limit: str, namespace: str, message: str) -> None:
        self._item: RateLimitItem = parse_rate_limit(limit)
        self._namespace = namespace
        self._message = message
        self._limiter = MovingWindowRateLimiter(MemoryStorage())

    def check(self, client_key: str) -> None:
        """Count one attempt; raise `RateLimitedError` when the client is over the limit."""
        if self._limiter.hit(self._item, self._namespace, client_key):
            return
        stats = self._limiter.get_window_stats(self._item, self._namespace, client_key)
        retry_after = math.ceil(stats.reset_time - time.time())
        raise RateLimitedError(self._message, retry_after)
