"""Token-bucket rate limiter for MCP tool invocations.

Prevents exceeding exchange API rate limits by gating outbound calls
through a token bucket that refills at a configured rate.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimiterStats:
    """Observable statistics for a rate limiter."""

    name: str
    tokens_available: float
    max_tokens: float
    refill_rate: float
    total_allowed: int
    total_throttled: int


class TokenBucketRateLimiter:
    """Token-bucket rate limiter.

    Args:
        name: Identifier for logging.
        max_tokens: Maximum tokens in the bucket (burst capacity).
        refill_rate: Tokens added per second.

    Usage::

        limiter = TokenBucketRateLimiter("aster_api", max_tokens=10, refill_rate=2.0)

        if limiter.acquire():
            # proceed with API call
            ...
        else:
            # throttled — back off
            ...
    """

    def __init__(
        self,
        name: str,
        max_tokens: float = 10.0,
        refill_rate: float = 2.0,
    ) -> None:
        self.name = name
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate

        self._tokens = max_tokens
        self._last_refill = time.monotonic()
        self._total_allowed = 0
        self._total_throttled = 0
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> bool:
        """Try to acquire tokens. Returns True if allowed, False if throttled."""
        with self._lock:
            self._refill()

            if self._tokens >= tokens:
                self._tokens -= tokens
                self._total_allowed += 1
                return True

            self._total_throttled += 1
            logger.debug(
                "Rate limiter throttled",
                extra={
                    "extra_json": {
                        "limiter": self.name,
                        "available": round(self._tokens, 2),
                        "requested": tokens,
                    }
                },
            )
            return False

    def wait_and_acquire(self, tokens: float = 1.0, timeout: float = 5.0) -> bool:
        """Block until tokens are available or timeout is reached."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.acquire(tokens):
                return True
            time.sleep(0.05)
        return False

    def stats(self) -> RateLimiterStats:
        """Return observable statistics snapshot."""
        with self._lock:
            self._refill()
            return RateLimiterStats(
                name=self.name,
                tokens_available=round(self._tokens, 2),
                max_tokens=self.max_tokens,
                refill_rate=self.refill_rate,
                total_allowed=self._total_allowed,
                total_throttled=self._total_throttled,
            )

    def _refill(self) -> None:
        """Add tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.max_tokens, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now


# --- Convenience: per-service limiter registry ---

_limiters: dict[str, TokenBucketRateLimiter] = {}
_registry_lock = threading.Lock()


def get_limiter(
    name: str,
    max_tokens: float = 10.0,
    refill_rate: float = 2.0,
) -> TokenBucketRateLimiter:
    """Get or create a named rate limiter (singleton per name)."""
    with _registry_lock:
        if name not in _limiters:
            _limiters[name] = TokenBucketRateLimiter(
                name=name,
                max_tokens=max_tokens,
                refill_rate=refill_rate,
            )
        return _limiters[name]
