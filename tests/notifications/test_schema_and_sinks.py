"""Unit tests for notification schema and delivery sinks."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from companion.notifications.schema import (
    NotificationCategory,
    NotificationPayload,
    NotificationSeverity,
)
from companion.notifications.sinks import ConsoleSink, InMemorySink, NotificationSink


def test_notification_payload_creation() -> None:
    now = datetime.now(timezone.utc)
    payload = NotificationPayload.create(
        title="Low Life Warning",
        message="Unreserved life dropped below 15%",
        severity=NotificationSeverity.CRITICAL,
        category=NotificationCategory.SURVIVAL,
    )
    assert payload.id is not None
    assert payload.title == "Low Life Warning"
    assert payload.severity == NotificationSeverity.CRITICAL
    assert payload.category == NotificationCategory.SURVIVAL
    assert payload.dedupe_key is not None


def test_in_memory_sink() -> None:
    sink = InMemorySink()
    assert isinstance(sink, NotificationSink)

    payload = NotificationPayload.create(
        title="Test Alert",
        message="Test Message",
        severity=NotificationSeverity.INFO,
        category=NotificationCategory.OPTIMIZATION,
    )

    assert sink.send(payload) is True
    assert len(sink.notifications) == 1
    assert sink.notifications[0].title == "Test Alert"

    sink.clear()
    assert len(sink.notifications) == 0


def test_console_sink(capsys: pytest.CaptureFixture[str]) -> None:
    sink = ConsoleSink()
    assert isinstance(sink, NotificationSink)

    payload = NotificationPayload.create(
        title="Console Alert",
        message="Console details",
        severity=NotificationSeverity.WARNING,
        category=NotificationCategory.RULE_VIOLATION,
    )

    assert sink.send(payload) is True
    captured = capsys.readouterr()
    assert "[WARNING] [RULE_VIOLATION] Console Alert: Console details" in captured.out
