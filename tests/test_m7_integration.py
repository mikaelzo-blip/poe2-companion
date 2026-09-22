"""End-to-end integration test suite for Milestone 7 vision sensing and state reconciliation."""

from __future__ import annotations

from pathlib import Path
import pytest

from companion.observations.bus import ObservationBus
from companion.observations.schema import ObservationEvent, ObservationEventType, ObservationSource
from companion.state.provenance import VerificationState
from companion.state.reconciliation import reconcile_observation
from companion.state.schema import CharacterState
from companion.vision.budget import VisionBudgetConfig, VisionBudgetTracker
from companion.vision.cache import ScreenshotCache
from companion.vision.classifier import classify_screen
from companion.vision.parser import evaluate_verification_state, parse_character_panel
from companion.vision.privacy import VisionPrivacyConfig, get_privacy_disclosure, redact_sensitive_text
from companion.vision.schema import ScreenType


PANEL_TEXT = """
Character
Defences
Maximum Life: 1,500 / 1,500
Maximum Mana: 400 / 400
Spirit: 100 / 100
Armour: 1,200
Evasion Rating: 900
Resistances
Fire Resistance: 75%
Cold Resistance: 75%
Lightning Resistance: 75%
Chaos Resistance: 0%
"""


def test_m7_vision_end_to_end_pipeline(tmp_path: Path) -> None:
    # 1. Setup Vision Privacy and Budget
    privacy_cfg = VisionPrivacyConfig(mode="local", provider="mock-ocr")
    disclosure = get_privacy_disclosure(privacy_cfg)
    assert "remains local" in disclosure

    budget_cfg = VisionBudgetConfig(enabled=True, max_calls_per_hour=60, min_seconds_between_captures=1.0)
    tracker = VisionBudgetTracker(budget_cfg)
    cache = ScreenshotCache(cache_dir=tmp_path / "screenshots", ttl_minutes=15, max_mb=50)

    # 2. Capture Frame 1
    assert tracker.can_capture() is True
    tracker.consume()
    cache.store("capture_001", PANEL_TEXT.encode("utf-8"))

    # 3. Classify & Parse Frame 1
    raw_text_1 = cache.get("capture_001").decode("utf-8")
    clean_text_1 = redact_sensitive_text(raw_text_1)
    screen_type_1, conf_1 = classify_screen(clean_text_1)
    assert screen_type_1 == ScreenType.CHARACTER_PANEL
    stats_1 = parse_character_panel(clean_text_1)

    # 4. Capture Frame 2 (Corroboration)
    tracker.consume()
    cache.store("capture_002", PANEL_TEXT.encode("utf-8"))
    raw_text_2 = cache.get("capture_002").decode("utf-8")
    stats_2 = parse_character_panel(raw_text_2)

    # 5. Multi-Capture Semantic Verification
    final_stats, ver_state = evaluate_verification_state([stats_1, stats_2])
    assert ver_state == VerificationState.VERIFIED
    assert final_stats.fire_res == 75

    # 6. Publish to Observation Bus
    bus = ObservationBus()
    dispatched_events: list[ObservationEvent] = []
    bus.subscribe(None, lambda e: dispatched_events.append(e))

    obs_event = ObservationEvent.create(
        event_type=ObservationEventType.STAT_OBSERVATION,
        source=ObservationSource.VISION,
        character_id="char_merc_01",
        payload={
            "screen_type": screen_type_1.value,
            "verification_state": ver_state.value,
            "resistances": {
                "fire": final_stats.fire_res,
                "cold": final_stats.cold_res,
                "lightning": final_stats.lightning_res,
                "chaos": final_stats.chaos_res,
            },
        },
    )
    bus.publish(obs_event)
    assert len(dispatched_events) == 1

    # 7. Reconcile with CharacterState
    char = CharacterState.create_initial(
        character_id="char_merc_01",
        character_name="MercValkyrie",
    )
    assert char.resistances["fire"].value == 0
    assert char.resistances["fire"].verification_state == VerificationState.UNKNOWN

    updated_char = reconcile_observation(char, obs_event)
    assert updated_char.resistances["fire"].value == 75
    assert updated_char.resistances["fire"].verification_state == VerificationState.VERIFIED
    assert updated_char.resistances["fire"].source == "vision"
    assert updated_char.resistances["cold"].value == 75
    assert updated_char.resistances["lightning"].value == 75
    assert updated_char.resistances["chaos"].value == 0
