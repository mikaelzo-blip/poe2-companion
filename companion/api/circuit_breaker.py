"""Resilience circuit breaker guarding against 4xx/rate-limit errors from GGG official API."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import threading
from typing import Any


class CircuitState(str, Enum):
    """Circuit breaker tri-state."""
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class ApiCircuitBreaker:
    """Tracks consecutive 4xx response codes and trips to OPEN to prevent bans."""

    TARGETED_4XX: frozenset[int] = frozenset({401, 403, 429})

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 300.0) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative")
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.opened_at: datetime | None = None
        self.last_failure_status: int | None = None
        self._half_open_probe_in_flight = False
        self._lock = threading.RLock()

    def can_execute(self, now: datetime | None = None) -> bool:
        """Check whether outgoing requests are permitted."""
        current_time = now or datetime.now(timezone.utc)

        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                if self.opened_at is not None:
                    elapsed = (current_time - self.opened_at).total_seconds()
                    if elapsed >= self.cooldown_seconds:
                        self.state = CircuitState.HALF_OPEN
                        self._half_open_probe_in_flight = True
                        return True
                return False

            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_probe_in_flight:
                    return False
                self._half_open_probe_in_flight = True
                return True

            return False

    def record_success(self) -> None:
        """Record successful request, resetting state to CLOSED."""
        with self._lock:
            self.consecutive_failures = 0
            self.state = CircuitState.CLOSED
            self.opened_at = None
            self.last_failure_status = None
            self._half_open_probe_in_flight = False

    def record_failure(self, status_code: int, now: datetime | None = None) -> None:
        """Record failed request, tripping circuit breaker if threshold is reached."""
        current_time = now or datetime.now(timezone.utc)
        with self._lock:
            # Only the documented auth/rate-limit responses contribute to the breaker.
            if status_code not in self.TARGETED_4XX:
                self.consecutive_failures = 0
                self.state = CircuitState.CLOSED
                self.opened_at = None
                self.last_failure_status = None
                self._half_open_probe_in_flight = False
                return

            self.last_failure_status = status_code
            self.consecutive_failures += 1
            self._half_open_probe_in_flight = False
            if self.consecutive_failures >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = current_time

    def to_dict(self) -> dict[str, Any]:
        """Serialize circuit breaker state for diagnostics."""
        return {
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "failure_threshold": self.failure_threshold,
            "cooldown_seconds": self.cooldown_seconds,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "last_failure_status": self.last_failure_status,
        }
