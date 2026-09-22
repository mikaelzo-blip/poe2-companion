"""Unit tests for Milestone 10 4xx API circuit breaker."""

from datetime import datetime, timedelta, timezone
import pytest
from companion.api.circuit_breaker import ApiCircuitBreaker, CircuitState


def test_circuit_breaker_initial_state() -> None:
    cb = ApiCircuitBreaker(failure_threshold=3, cooldown_seconds=60)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True


def test_circuit_breaker_trips_on_consecutive_4xx() -> None:
    now = datetime.now(timezone.utc)
    cb = ApiCircuitBreaker(failure_threshold=3, cooldown_seconds=60)

    # 1st 4xx
    cb.record_failure(status_code=429, now=now)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute(now=now) is True

    # 2nd 4xx
    cb.record_failure(status_code=401, now=now)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute(now=now) is True

    # 3rd 4xx -> Tripped!
    cb.record_failure(status_code=403, now=now)
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute(now=now) is False


def test_circuit_breaker_cooldown_to_half_open_and_reset() -> None:
    start = datetime.now(timezone.utc)
    cb = ApiCircuitBreaker(failure_threshold=2, cooldown_seconds=60)

    cb.record_failure(status_code=429, now=start)
    cb.record_failure(status_code=429, now=start)
    assert cb.state == CircuitState.OPEN

    # 30 seconds later (within cooldown) -> still OPEN
    t_30s = start + timedelta(seconds=30)
    assert cb.can_execute(now=t_30s) is False

    # 65 seconds later (after cooldown) -> transitions to HALF_OPEN
    t_65s = start + timedelta(seconds=65)
    assert cb.can_execute(now=t_65s) is True
    assert cb.state == CircuitState.HALF_OPEN

    # Canary request succeeds -> resets to CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.consecutive_failures == 0


def test_circuit_breaker_only_allows_one_half_open_probe() -> None:
    start = datetime.now(timezone.utc)
    cb = ApiCircuitBreaker(failure_threshold=1, cooldown_seconds=60)
    cb.record_failure(429, now=start)

    after_cooldown = start + timedelta(seconds=61)
    assert cb.can_execute(now=after_cooldown) is True
    assert cb.can_execute(now=after_cooldown) is False
    cb.record_success()
    assert cb.can_execute(now=after_cooldown) is True


def test_circuit_breaker_success_resets_failure_count() -> None:
    now = datetime.now(timezone.utc)
    cb = ApiCircuitBreaker(failure_threshold=3, cooldown_seconds=60)

    cb.record_failure(status_code=429, now=now)
    assert cb.consecutive_failures == 1

    cb.record_success()
    assert cb.consecutive_failures == 0
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_only_counts_targeted_4xx_and_non_4xx_breaks_sequence() -> None:
    now = datetime.now(timezone.utc)
    cb = ApiCircuitBreaker(failure_threshold=2, cooldown_seconds=60)

    cb.record_failure(status_code=400, now=now)
    assert cb.consecutive_failures == 0
    cb.record_failure(status_code=429, now=now)
    assert cb.consecutive_failures == 1
    cb.record_success()
    cb.record_failure(status_code=403, now=now)
    assert cb.consecutive_failures == 1
    assert cb.state == CircuitState.CLOSED
