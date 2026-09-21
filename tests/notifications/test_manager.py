"""Unit tests for NotificationManager queue batching and safe-zone flush."""

from __future__ import annotations

import pytest

from companion.notifications.manager import NotificationDispatchStatus, NotificationManager
from companion.notifications.schema import (
    NotificationCategory,
    NotificationPayload,
    NotificationSeverity,
)
from companion.notifications.sinks import InMemorySink


def test_notification_manager_immediate_delivery_safe_zone() -> None:
    sink = InMemorySink()
    manager = NotificationManager(sinks=[sink])

    payload = NotificationPayload.create(
        title="Optimization Suggestion",
        message="Upgrade life ring",
        severity=NotificationSeverity.INFO,
        category=NotificationCategory.OPTIMIZATION,
    )

    res = manager.dispatch(payload, current_zone="The Clear Fell Encampment")
    assert res.status == NotificationDispatchStatus.DELIVERED
    assert len(sink.notifications) == 1
    assert len(manager.queued_alerts) == 0


def test_notification_manager_immediate_delivery_critical_in_combat() -> None:
    sink = InMemorySink()
    manager = NotificationManager(sinks=[sink])

    payload = NotificationPayload.create(
        title="Immediate Danger",
        message="Life < 15%",
        severity=NotificationSeverity.CRITICAL,
        category=NotificationCategory.SURVIVAL,
    )

    # In hostile combat zone
    res = manager.dispatch(payload, current_zone="The Grim Tangle")
    assert res.status == NotificationDispatchStatus.DELIVERED
    assert len(sink.notifications) == 1
    assert len(manager.queued_alerts) == 0


def test_notification_manager_queue_in_combat_and_flush_on_safe_zone() -> None:
    sink = InMemorySink()
    manager = NotificationManager(sinks=[sink])

    advisory = NotificationPayload.create(
        title="Gem Socket Advisory",
        message="Socket added gem in town",
        severity=NotificationSeverity.WARNING,
        category=NotificationCategory.RULE_VIOLATION,
    )

    # 1. In combat zone -> queued
    res = manager.dispatch(advisory, current_zone="The Riverbank")
    assert res.status == NotificationDispatchStatus.QUEUED
    assert len(sink.notifications) == 0
    assert len(manager.queued_alerts) == 1

    # 2. Moving to another combat zone -> remains queued
    flushed = manager.on_zone_entered("The Mud Flats")
    assert len(flushed) == 0
    assert len(manager.queued_alerts) == 1
    assert len(sink.notifications) == 0

    # 3. Moving to safe zone (Town) -> flushes queued alert
    flushed = manager.on_zone_entered("Town of Ogham")
    assert len(flushed) == 1
    assert flushed[0].title == "Gem Socket Advisory"
    assert len(manager.queued_alerts) == 0
    assert len(sink.notifications) == 1


def test_notification_manager_cooldown_deduplication() -> None:
    sink = InMemorySink()
    manager = NotificationManager(sinks=[sink])

    payload1 = NotificationPayload.create(
        title="Repeated Alert",
        message="Details",
        severity=NotificationSeverity.CRITICAL,
        category=NotificationCategory.SURVIVAL,
        dedupe_key="dedupe_123",
    )

    payload2 = NotificationPayload.create(
        title="Repeated Alert",
        message="Details",
        severity=NotificationSeverity.CRITICAL,
        category=NotificationCategory.SURVIVAL,
        dedupe_key="dedupe_123",
    )

    res1 = manager.dispatch(payload1, current_zone="The Riverbank")
    assert res1.status == NotificationDispatchStatus.DELIVERED

    # Immediate second alert with same dedupe_key dropped
    res2 = manager.dispatch(payload2, current_zone="The Riverbank")
    assert res2.status == NotificationDispatchStatus.COOLDOWN_DROPPED
    assert len(sink.notifications) == 1
