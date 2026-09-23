"""Bounded safe-zone notification queue and runtime notification manager."""

from __future__ import annotations

from typing import Any

from companion.notifications.policy import CooldownTracker, SafeZonePolicy
from companion.notifications.schema import NotificationPayload, NotificationSeverity
from companion.notifications.sinks import NotificationSink


class BoundedNotificationQueue:
    """Bounded, semantically-deduplicated safe-zone notification queue."""

    def __init__(self, max_depth: int = 20) -> None:
        self.max_depth = max_depth
        self._items: list[NotificationPayload] = []

    def __len__(self) -> int:
        return len(self._items)

    def peek_all(self) -> list[NotificationPayload]:
        return list(self._items)

    def push(self, payload: NotificationPayload) -> None:
        """Push alert into queue with in-place replacement and max-depth bounding."""
        for i, existing in enumerate(self._items):
            if existing.dedupe_key == payload.dedupe_key:
                # In-place semantic replacement
                self._items[i] = payload
                return

        # Not in queue; check depth limit
        if len(self._items) >= self.max_depth:
            # Drop oldest non-critical alert
            drop_index: int | None = None
            for idx, item in enumerate(self._items):
                if item.severity != NotificationSeverity.CRITICAL:
                    drop_index = idx
                    break

            if drop_index is not None:
                self._items.pop(drop_index)
            else:
                self._items.pop(0)

        self._items.append(payload)

    def pop_all(self) -> list[NotificationPayload]:
        """Drain and return all queued alerts."""
        items = list(self._items)
        self._items.clear()
        return items


class RuntimeNotificationManager:
    """Manages runtime notification delivery with backfill suppression and safe-zone buffering."""

    def __init__(
        self,
        sinks: list[NotificationSink] | None = None,
        policy: SafeZonePolicy | None = None,
        cooldown_tracker: CooldownTracker | None = None,
        suppress_notifications: bool = False,
        max_queue_depth: int = 20,
    ) -> None:
        self._sinks: list[NotificationSink] = sinks or []
        self._policy: SafeZonePolicy = policy or SafeZonePolicy()
        self._cooldown: CooldownTracker = cooldown_tracker or CooldownTracker()
        self._queue = BoundedNotificationQueue(max_depth=max_queue_depth)
        self.suppress_notifications: bool = suppress_notifications

    @property
    def queued_alerts(self) -> list[NotificationPayload]:
        return self._queue.peek_all()

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    def add_sink(self, sink: NotificationSink) -> None:
        self._sinks.append(sink)

    def dispatch(
        self,
        payload: NotificationPayload,
        current_zone: str | None,
    ) -> str:
        """Dispatch a notification adhering to backfill suppression, cooldown, and safe-zone buffering."""
        if self.suppress_notifications:
            return "SUPPRESSED"

        if self._cooldown.is_cooling_down(payload.dedupe_key):
            return "COOLDOWN_DROPPED"

        if self._policy.should_defer_alert(payload.severity, current_zone):
            self._queue.push(payload)
            return "QUEUED"

        self._deliver(payload)
        return "DELIVERED"

    def on_zone_entered(self, zone_name: str) -> list[NotificationPayload]:
        """Flush queued safe-zone alerts upon entering a town or hideout."""
        if not self._policy.is_safe_zone(zone_name):
            return []

        flushed: list[NotificationPayload] = []
        queued_items = self._queue.pop_all()
        for alert in queued_items:
            if not self._cooldown.is_cooling_down(alert.dedupe_key):
                self._deliver(alert)
                flushed.append(alert)

        return flushed

    def _deliver(self, payload: NotificationPayload) -> None:
        """Deliver payload to all sinks isolating individual sink failures."""
        for sink in self._sinks:
            try:
                sink.send(payload)
            except Exception:
                pass
        self._cooldown.record_sent(payload.dedupe_key)
