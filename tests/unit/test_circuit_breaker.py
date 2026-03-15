"""Tests for circuit breaker, rate limiter, and graceful shutdown."""

from __future__ import annotations

import time

from aiswarm.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)
from aiswarm.resilience.rate_limiter import TokenBucketRateLimiter


class TestCircuitBreaker:
    def test_starts_closed(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED

    def test_allows_requests_when_closed(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=3)
        assert cb.allow_request()

    def test_opens_after_threshold_failures(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            cb.allow_request()
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_rejects_requests_when_open(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert not cb.allow_request()

    def test_transitions_to_half_open_after_timeout(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.06)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_allows_one_request(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure()
        time.sleep(0.06)
        assert cb.allow_request()

    def test_half_open_success_closes(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure()
        time.sleep(0.06)
        cb.allow_request()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure()
        time.sleep(0.06)
        cb.allow_request()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_manual_reset(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_stats(self) -> None:
        cb = CircuitBreaker("test_stats", failure_threshold=5)
        cb.record_success()
        cb.record_failure()
        stats = cb.stats()
        assert stats.name == "test_stats"
        assert stats.success_count == 1
        assert stats.failure_count == 1
        assert stats.total_calls == 2

    def test_rejection_tracking(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()
        cb.allow_request()  # rejected
        cb.allow_request()  # rejected
        stats = cb.stats()
        assert stats.total_rejections == 2


class TestTokenBucketRateLimiter:
    def test_allows_within_capacity(self) -> None:
        rl = TokenBucketRateLimiter("test", max_tokens=5, refill_rate=10)
        for _ in range(5):
            assert rl.acquire()

    def test_throttles_when_empty(self) -> None:
        rl = TokenBucketRateLimiter("test", max_tokens=2, refill_rate=0.001)
        assert rl.acquire()
        assert rl.acquire()
        assert not rl.acquire()

    def test_refills_over_time(self) -> None:
        rl = TokenBucketRateLimiter("test", max_tokens=2, refill_rate=100)
        rl.acquire()
        rl.acquire()
        time.sleep(0.05)
        assert rl.acquire()

    def test_wait_and_acquire(self) -> None:
        rl = TokenBucketRateLimiter("test", max_tokens=1, refill_rate=100)
        rl.acquire()  # exhaust
        # Should succeed after short wait due to high refill rate
        assert rl.wait_and_acquire(timeout=0.5)

    def test_wait_and_acquire_timeout(self) -> None:
        rl = TokenBucketRateLimiter("test", max_tokens=1, refill_rate=0.001)
        rl.acquire()
        # Should fail — very slow refill, short timeout
        assert not rl.wait_and_acquire(timeout=0.1)

    def test_stats(self) -> None:
        rl = TokenBucketRateLimiter("test_rl", max_tokens=3, refill_rate=1.0)
        rl.acquire()
        rl.acquire()
        stats = rl.stats()
        assert stats.name == "test_rl"
        assert stats.total_allowed == 2
        assert stats.max_tokens == 3

    def test_does_not_exceed_max_tokens(self) -> None:
        rl = TokenBucketRateLimiter("test", max_tokens=3, refill_rate=1000)
        time.sleep(0.1)  # Many tokens would accumulate
        stats = rl.stats()
        assert stats.tokens_available <= 3.0
