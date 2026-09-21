"""Notification manager coordinating safe-zone policy, deduplication, and sinks."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict

from companion.notifications.policy import CooldownTracker, SafeZonePolicy
from companion.notifications.schema import NotificationPayload
from companion.notifications.sinks import NotificationSink


class NotificationDispatchStatus(str, Enum):
    """Result status of dispatching a notification."""

    DELIVERED = "DELIVERED"
    QUEUED = "QUEUED"
    COOLDOWN_DROPPED = "COOLDOWN_DROPPED"


class NotificationDispatchResult(BaseModel):
    """Result details of a notification dispatch attempt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: NotificationDispatchStatus
    payload: NotificationPayload


class NotificationManager:
    """Coordinates policy checks, safe-zone queues, and sink deliveries."""

    def __init__(
        self,
        sinks: list[NotificationSink] | None = None,
        policy: SafeZonePolicy | None = None,
        cooldown_tracker: CooldownTracker | None = None,
    ) -> None:
        self._sinks: list[NotificationSink] = sinks or []
        self._policy: SafeZonePolicy = policy or SafeZonePolicy()
        self._cooldown: CooldownTracker = cooldown_tracker or CooldownTracker()
        self._safe_zone_queue: list[NotificationPayload] = []

    def add_sink(self, sink: NotificationSink) -> None:
        """Add a notification delivery sink."""
        self._sinks.append(sink)

    @property
    def queued_alerts(self) -> list[NotificationPayload]:
        """Return shallow copy of alerts queued for safe-zone delivery."""
        return list(self._safe_zone_queue)

    def dispatch(
        self, payload: NotificationPayload, current_zone: str | None
    ) -> NotificationDispatchResult:
        """Dispatch a notification payload adhering to deduplication and safe-zone rules."""
        # Check cooldown deduplication
        if self._cooldown.is_cooling_down(payload.dedupe_key):
            return NotificationDispatchResult(
                status=NotificationDispatchStatus.COOLDOWN_DROPPED,
                payload=payload,
            )

        # Check safe-zone deferral policy
        if self._policy.should_defer_alert(payload.severity, current_zone):
            self._safe_zone_queue.append(payload)
            return NotificationDispatchResult(
                status=NotificationDispatchStatus.QUEUED,
                payload=payload,
            )

        # Deliver immediately to all sinks
        self._deliver(payload)
        return NotificationDispatchResult(
            status=NotificationDispatchStatus.DELIVERED,
            payload=payload,
        )

    def on_zone_entered(self, zone_name: str) -> list[NotificationPayload]:
        """Trigger safe-zone check upon zone transition and flush queued alerts if safe."""
        if not self._policy.is_safe_zone(zone_name):
            return []

        flushed: list[NotificationPayload] = []
        while self._safe_zone_queue:
            alert = self._safe_zone_queue.pop(0)
            # Re-check cooldown before flushing
            if not self._cooldown.is_cooling_down(alert.dedupe_key):
                self._deliver(alert)
                flushed.append(alert)

        return flushed

    def _deliver(self, payload: NotificationPayload) -> None:
        """Deliver payload to all sinks and update cooldown."""
        for sink in self._sinks:
            sink.send(payload)
        self._cooldown.record_sent(payload.dedupe_key)
