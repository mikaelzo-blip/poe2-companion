"""Notifications package for low-friction game alerts and safe-zone management."""

from __future__ import annotations

from companion.notifications.schema import (
    NotificationCategory,
    NotificationPayload,
    NotificationSeverity,
)
from companion.notifications.sinks import (
    ConsoleSink,
    InMemorySink,
    NotificationSink,
)

__all__ = [
    "ConsoleSink",
    "InMemorySink",
    "NotificationCategory",
    "NotificationPayload",
    "NotificationSeverity",
    "NotificationSink",
]
