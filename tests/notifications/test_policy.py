"""Unit tests for SafeZonePolicy and CooldownTracker."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from companion.notifications.policy import CooldownTracker, SafeZonePolicy
from companion.notifications.schema import NotificationSeverity


def test_safe_zone_classification() -> None:
    policy = SafeZonePolicy()

    # Known safe zones
    assert policy.is_safe_zone("The Clear Fell Encampment") is True
    assert policy.is_safe_zone("Town of Ogham") is True
    assert policy.is_safe_zone("Hideout") is True
    assert policy.is_safe_zone("Kingsmarch") is True
    assert policy.is_safe_zone("Ardura Caravan") is True

    # Hostile / combat zones
    assert policy.is_safe_zone("The Riverbank") is False
    assert policy.is_safe_zone("The Grim Tangle") is False
    assert policy.is_safe_zone("Cemetery of the First Ones") is False
    assert policy.is_safe_zone(None) is False
    assert policy.is_safe_zone("Unknown Area") is False


def test_should_defer_alert() -> None:
    policy = SafeZonePolicy()

    # Critical alert NEVER deferred anywhere
    assert policy.should_defer_alert(NotificationSeverity.CRITICAL, "The Riverbank") is False
    assert policy.should_defer_alert(NotificationSeverity.CRITICAL, "Hideout") is False

    # Non-critical alert deferred in combat zone
    assert policy.should_defer_alert(NotificationSeverity.WARNING, "The Grim Tangle") is True
    assert policy.should_defer_alert(NotificationSeverity.INFO, "The Grim Tangle") is True

    # Non-critical alert NOT deferred in safe zone
    assert policy.should_defer_alert(NotificationSeverity.WARNING, "Hideout") is False
    assert policy.should_defer_alert(NotificationSeverity.INFO, "Town of Ogham") is False


def test_cooldown_tracker() -> None:
    tracker = CooldownTracker(cooldown_seconds=60.0)
    t0 = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)

    # Initial check: not cooling down
    assert tracker.is_cooling_down("key_1", now=t0) is False

    # Record send
    tracker.record_sent("key_1", now=t0)
    assert tracker.is_cooling_down("key_1", now=t0) is True

    # Check at 30 seconds: still cooling down
    t1 = t0 + timedelta(seconds=30)
    assert tracker.is_cooling_down("key_1", now=t1) is True

    # Check at 61 seconds: cooldown expired
    t2 = t0 + timedelta(seconds=61)
    assert tracker.is_cooling_down("key_1", now=t2) is False
