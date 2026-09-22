"""Unit tests for vision schema, privacy disclosures, and budget tracking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from companion.state.provenance import VerificationState
from companion.vision.budget import VisionBudgetConfig, VisionBudgetTracker
from companion.vision.privacy import VisionPrivacyConfig, get_privacy_disclosure, redact_sensitive_text
from companion.vision.schema import CharacterPanelStats, ScreenType, VisionExtractionResult


def test_vision_schema_models() -> None:
    stats = CharacterPanelStats(
        life=1200,
        mana=350,
        spirit=100,
        armour=450,
        evasion=800,
        fire_res=75,
        cold_res=60,
        lightning_res=75,
        chaos_res=-10,
    )
    result = VisionExtractionResult(
        screen_type=ScreenType.CHARACTER_PANEL,
        stats=stats,
        verification_state=VerificationState.VERIFIED,
        confidence=0.98,
    )
    assert result.screen_type == ScreenType.CHARACTER_PANEL
    assert result.stats.fire_res == 75
    assert result.verification_state == VerificationState.VERIFIED


def test_vision_privacy_disclosure_and_redaction() -> None:
    cloud_config = VisionPrivacyConfig(mode="cloud", provider="custom-vision")
    disclosure = get_privacy_disclosure(cloud_config)
    assert "transmitted to the configured model provider" in disclosure

    local_config = VisionPrivacyConfig(mode="local", provider="local-onnx")
    local_disc = get_privacy_disclosure(local_config)
    assert "remains local" in local_disc

    raw_text = "Player Character: SlayerOfKitava. Whisper from Bob: Hello."
    redacted = redact_sensitive_text(raw_text)
    assert "SlayerOfKitava" not in redacted
    assert "Whisper from" not in redacted


def test_vision_budget_tracker_hourly_limit() -> None:
    config = VisionBudgetConfig(
        enabled=True,
        max_calls_per_hour=3,
        min_seconds_between_captures=1.0,
    )
    tracker = VisionBudgetTracker(config)
    t0 = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)

    assert tracker.can_capture(now=t0) is True
    tracker.consume(now=t0)

    t1 = t0 + timedelta(seconds=2)
    assert tracker.can_capture(now=t1) is True
    tracker.consume(now=t1)

    t2 = t1 + timedelta(seconds=2)
    assert tracker.can_capture(now=t2) is True
    tracker.consume(now=t2)

    # Exceeded 3 calls per hour
    t3 = t2 + timedelta(seconds=2)
    assert tracker.can_capture(now=t3) is False

    # After 1 hour, older calls expire
    t4 = t0 + timedelta(minutes=61)
    assert tracker.can_capture(now=t4) is True


def test_vision_budget_tracker_inter_capture_cooldown() -> None:
    config = VisionBudgetConfig(
        enabled=True,
        max_calls_per_hour=100,
        min_seconds_between_captures=15.0,
    )
    tracker = VisionBudgetTracker(config)
    t0 = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)

    tracker.consume(now=t0)

    # 10 seconds later: rejected due to 15s cooldown
    t1 = t0 + timedelta(seconds=10)
    assert tracker.can_capture(now=t1) is False

    # 16 seconds later: allowed
    t2 = t0 + timedelta(seconds=16)
    assert tracker.can_capture(now=t2) is True
