"""
Rate limiter — simple in-memory sliding window counter.

limits how many queries a session can run per minute.
this is defense against runaway loops or abuse, not a production
rate limiter (that would need Redis or similar).
"""

import time
import logging
from collections import defaultdict

from app.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """sliding window rate limiter — tracks calls per session per minute."""

    def __init__(self, max_per_minute: int | None = None):
        self.max_per_minute = max_per_minute or settings.rate_limit_per_minute
        # session_id -> list of timestamps
        self._windows: dict[str, list[float]] = defaultdict(list)

    def check(self, session_id: str = "default") -> bool:
        """returns True if the request is allowed, False if rate limited."""
        now = time.time()
        window = self._windows[session_id]

        # drop entries older than 60 seconds
        window[:] = [t for t in window if now - t < 60]

        if len(window) >= self.max_per_minute:
            logger.warning(
                f"Rate limit hit for session '{session_id}': "
                f"{len(window)}/{self.max_per_minute} requests in the last minute"
            )
            return False

        window.append(now)
        return True

    def reset(self, session_id: str = "default") -> None:
        """clear the window for a session — useful for testing."""
        self._windows.pop(session_id, None)


# shared instance
rate_limiter = RateLimiter()
