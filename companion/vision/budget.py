"""Vision budget management and capture rate limiting."""

from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict


class VisionBudgetConfig(BaseModel):
    """Configuration constraints for vision calls."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = True
    max_calls_per_hour: int = 120
    min_seconds_between_captures: float = 15.0
    screenshot_cache_ttl_minutes: int = 30
    screenshot_cache_max_mb: int = 500


class VisionBudgetTracker:
    """Tracks vision call timestamps and enforces budget constraints."""

    def __init__(self, config: VisionBudgetConfig | None = None) -> None:
        self.config = config or VisionBudgetConfig()
        self._history: list[datetime] = []

    def can_capture(self, now: datetime | None = None) -> bool:
        """Check whether a new capture is allowed within current budget and cooldown."""
        if not self.config.enabled:
            return False

        current_time = now or datetime.now(timezone.utc)
        self._prune(current_time)

        # 1. Hourly call limit check
        if len(self._history) >= self.config.max_calls_per_hour:
            return False

        # 2. Inter-capture cooldown check
        if self._history:
            last_call = self._history[-1]
            elapsed = (current_time - last_call).total_seconds()
            if elapsed < self.config.min_seconds_between_captures:
                return False

        return True

    def consume(self, now: datetime | None = None) -> bool:
        """Record and consume a capture slot if allowed."""
        current_time = now or datetime.now(timezone.utc)
        if not self.can_capture(current_time):
            return False

        self._history.append(current_time)
        return True

    def _prune(self, current_time: datetime) -> None:
        """Remove calls older than 60 minutes."""
        one_hour_ago = current_time.timestamp() - 3600
        self._history = [t for t in self._history if t.timestamp() >= one_hour_ago]

    @property
    def calls_in_past_hour(self) -> int:
        now = datetime.now(timezone.utc)
        self._prune(now)
        return len(self._history)
