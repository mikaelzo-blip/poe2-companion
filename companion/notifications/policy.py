"""Safe-zone classification and cooldown policies for notifications."""

from __future__ import annotations

from datetime import datetime, timezone
import re

from companion.notifications.schema import NotificationSeverity


class SafeZonePolicy:
    """Classifies game zones and determines notification deferral."""

    # Substring keywords indicating non-combat safe environments
    SAFE_ZONE_KEYWORDS: tuple[str, ...] = (
        "encampment",
        "town",
        "hideout",
        "caravan",
        "kingsmarch",
        "ogham",
    )

    def is_safe_zone(self, zone_name: str | None) -> bool:
        """Return True if zone is a known safe zone or town."""
        if not zone_name:
            return False

        normalized = zone_name.strip().lower()
        for kw in self.SAFE_ZONE_KEYWORDS:
            if kw in normalized:
                return True
        return False

    def should_defer_alert(
        self, severity: NotificationSeverity, zone_name: str | None
    ) -> bool:
        """Return True if alert should be queued instead of delivered immediately."""
        # Critical alerts ALWAYS bypass safe-zone queue
        if severity == NotificationSeverity.CRITICAL:
            return False

        # In safe zone, alerts are delivered without deferral
        if self.is_safe_zone(zone_name):
            return False

        # Non-critical alert in hostile / combat zone is deferred
        return True


class CooldownTracker:
    """Tracks deduplication cooldowns for alert keys."""

    def __init__(self, cooldown_seconds: float = 120.0) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._last_sent: dict[str, datetime] = {}

    def is_cooling_down(self, key: str, now: datetime | None = None) -> bool:
        """Check if an alert key is within active cooldown window."""
        if key not in self._last_sent:
            return False

        current_time = now or datetime.now(timezone.utc)
        last_time = self._last_sent[key]
        elapsed = (current_time - last_time).total_seconds()
        return elapsed < self.cooldown_seconds

    def record_sent(self, key: str, now: datetime | None = None) -> None:
        """Record that an alert was sent at the current time."""
        self._last_sent[key] = now or datetime.now(timezone.utc)

    def prune(self, max_age_seconds: float | None = None) -> None:
        """Remove entries older than the retention threshold."""
        threshold = max_age_seconds or (self.cooldown_seconds * 2)
        now = datetime.now(timezone.utc)
        keys_to_delete = [
            k
            for k, ts in self._last_sent.items()
            if (now - ts).total_seconds() > threshold
        ]
        for k in keys_to_delete:
            del self._last_sent[k]
