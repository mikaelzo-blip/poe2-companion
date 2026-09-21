"""Delivery sinks for companion notifications."""

from __future__ import annotations

import sys
from typing import Protocol, runtime_checkable

from companion.notifications.schema import NotificationPayload


@runtime_checkable
class NotificationSink(Protocol):
    """Interface for delivering notifications to an external channel."""

    def send(self, payload: NotificationPayload) -> bool:
        """Deliver notification payload. Return True on success."""
        ...


class InMemorySink:
    """In-memory sink recording all delivered notifications."""

    def __init__(self) -> None:
        self._notifications: list[NotificationPayload] = []

    @property
    def notifications(self) -> list[NotificationPayload]:
        return list(self._notifications)

    def send(self, payload: NotificationPayload) -> bool:
        self._notifications.append(payload)
        return True

    def clear(self) -> None:
        self._notifications.clear()


class ConsoleSink:
    """Console sink printing alerts directly to stdout / stderr."""

    def __init__(self, use_stderr: bool = False) -> None:
        self._stream = sys.stderr if use_stderr else sys.stdout

    def send(self, payload: NotificationPayload) -> bool:
        line = f"[{payload.severity.value}] [{payload.category.value}] {payload.title}: {payload.message}\n"
        self._stream.write(line)
        self._stream.flush()
        return True
