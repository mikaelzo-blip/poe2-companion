"""Unit tests for bounded safe-zone notification queue and backfill suppression."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from companion.notifications.schema import (
    NotificationCategory,
    NotificationPayload,
    NotificationSeverity,
)
from companion.runtime.notifications import BoundedNotificationQueue, RuntimeNotificationManager


def test_in_place_replacement_for_same_dedupe_key() -> None:
    queue = BoundedNotificationQueue(max_depth=20)

    p1 = NotificationPayload.create(
        title="Passive Alert",
        message="Take Heavy Projectiles",
        severity=NotificationSeverity.INFO,
        category=NotificationCategory.OPTIMIZATION,
        dedupe_key="passive:heavy_projectiles",
    )
    p2 = NotificationPayload.create(
        title="Passive Alert",
        message="Take Heavy Projectiles (Urgent)",
        severity=NotificationSeverity.WARNING,
        category=NotificationCategory.OPTIMIZATION,
        dedupe_key="passive:heavy_projectiles",
    )

    queue.push(p1)
    assert len(queue) == 1
    assert queue.peek_all()[0].message == "Take Heavy Projectiles"

    queue.push(p2)
    assert len(queue) == 1  # In-place replacement, length unchanged!
    assert queue.peek_all()[0].message == "Take Heavy Projectiles (Urgent)"
    assert queue.peek_all()[0].severity == NotificationSeverity.WARNING


def test_queue_capping_at_max_depth() -> None:
    queue = BoundedNotificationQueue(max_depth=20)

    # Push 20 distinct alerts
    for i in range(20):
        p = NotificationPayload.create(
            title=f"Alert {i}",
            message=f"Message {i}",
            severity=NotificationSeverity.INFO,
            category=NotificationCategory.OPTIMIZATION,
            dedupe_key=f"key_{i}",
        )
        queue.push(p)

    assert len(queue) == 20

    # Push 21st alert: must drop oldest non-critical alert to maintain max_depth=20
    p21 = NotificationPayload.create(
        title="Alert 20",
        message="Message 20",
        severity=NotificationSeverity.INFO,
        category=NotificationCategory.OPTIMIZATION,
        dedupe_key="key_20",
    )
    queue.push(p21)
    assert len(queue) == 20
    # Oldest (key_0) dropped, key_20 present
    keys = [item.dedupe_key for item in queue.peek_all()]
    assert "key_0" not in keys
    assert "key_20" in keys


def test_runtime_notification_manager_backfill_suppression() -> None:
    sink = MagicMock()
    mgr = RuntimeNotificationManager(sinks=[sink], suppress_notifications=True)

    payload = NotificationPayload.create(
        title="Level Up",
        message="Reached level 10",
        severity=NotificationSeverity.INFO,
        category=NotificationCategory.TRANSITION,
        dedupe_key="level:10",
    )

    # In safe zone with suppression active
    status = mgr.dispatch(payload, current_zone="The Riverbank")
    assert status == "SUPPRESSED"
    sink.send.assert_not_called()
    assert len(mgr.queued_alerts) == 0

    # Unset suppression (transition to live mode)
    mgr.suppress_notifications = False
    status_live = mgr.dispatch(payload, current_zone="The Riverbank")
    # Non-safe combat zone -> queued
    assert status_live == "QUEUED"
    assert len(mgr.queued_alerts) == 1
