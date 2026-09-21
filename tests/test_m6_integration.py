"""End-to-end integration tests for Milestone 6 notification system and session recap."""

from __future__ import annotations

from pathlib import Path
import pytest

from companion.notifications.manager import (
    NotificationDispatchStatus,
    NotificationManager,
)
from companion.notifications.schema import (
    NotificationCategory,
    NotificationPayload,
    NotificationSeverity,
)
from companion.notifications.sinks import InMemorySink
from companion.observations.schema import (
    ObservationEvent,
    ObservationEventType,
    ObservationSource,
)
from companion.recap.generator import generate_session_recap
from companion.state.history import JourneyHistoryLogger
from companion.state.provenance import ProvenancedField, VerificationState
from companion.state.schema import CharacterState


def test_m6_end_to_end_notification_lifecycle_and_recap(tmp_path: Path) -> None:
    # 1. Setup environment and character
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True)
    history_logger = JourneyHistoryLogger(runtime_dir / "journey_history.jsonl")

    char = CharacterState.create_initial("hero_m6", "M6Hero")
    char.level = ProvenancedField.create(14, "m6_test", VerificationState.VERIFIED)

    sink = InMemorySink()
    manager = NotificationManager(sinks=[sink])

    # 2. Player enters combat zone
    combat_zone = "The Riverbank"
    history_logger.record_event(
        ObservationEvent.create(
            event_type=ObservationEventType.ZONE_TRANSITION,
            source=ObservationSource.CLIENT_LOG,
            character_id=char.character_id,
            payload={"zone": combat_zone},
        )
    )

    # 3. Critical alert (e.g. Life < 15%) dispatched in combat zone
    critical_alert = NotificationPayload.create(
        title="Immediate Survival Risk",
        message="Unreserved Life < 15%",
        severity=NotificationSeverity.CRITICAL,
        category=NotificationCategory.SURVIVAL,
    )
    res_crit = manager.dispatch(critical_alert, current_zone=combat_zone)
    assert res_crit.status == NotificationDispatchStatus.DELIVERED
    assert len(sink.notifications) == 1
    assert sink.notifications[0].title == "Immediate Survival Risk"
    assert len(manager.queued_alerts) == 0

    # 4. Non-critical advisory alert dispatched in combat zone
    advisory_alert = NotificationPayload.create(
        title="Passive Tree Optimization",
        message="Path towards Iron Reflexes available",
        severity=NotificationSeverity.INFO,
        category=NotificationCategory.OPTIMIZATION,
    )
    res_adv = manager.dispatch(advisory_alert, current_zone=combat_zone)
    assert res_adv.status == NotificationDispatchStatus.QUEUED
    assert len(sink.notifications) == 1  # Not delivered yet
    assert len(manager.queued_alerts) == 1

    # 5. Combat zone transition: remains queued
    hostile_zone_2 = "The Mud Flats"
    history_logger.record_event(
        ObservationEvent.create(
            event_type=ObservationEventType.ZONE_TRANSITION,
            source=ObservationSource.CLIENT_LOG,
            character_id=char.character_id,
            payload={"zone": hostile_zone_2},
        )
    )
    flushed_combat = manager.on_zone_entered(hostile_zone_2)
    assert len(flushed_combat) == 0
    assert len(manager.queued_alerts) == 1
    assert len(sink.notifications) == 1

    # 6. Safe zone transition: Town of Ogham
    safe_zone = "Town of Ogham"
    history_logger.record_event(
        ObservationEvent.create(
            event_type=ObservationEventType.ZONE_TRANSITION,
            source=ObservationSource.CLIENT_LOG,
            character_id=char.character_id,
            payload={"zone": safe_zone},
        )
    )
    flushed_safe = manager.on_zone_entered(safe_zone)
    assert len(flushed_safe) == 1
    assert flushed_safe[0].title == "Passive Tree Optimization"
    assert len(manager.queued_alerts) == 0
    assert len(sink.notifications) == 2

    # 7. Level-up and death events recorded
    history_logger.record_event(
        ObservationEvent.create(
            event_type=ObservationEventType.LEVEL_UP,
            source=ObservationSource.CLIENT_LOG,
            character_id=char.character_id,
            payload={"character_name": "M6Hero", "level": 15},
        )
    )
    history_logger.record_event(
        ObservationEvent.create(
            event_type=ObservationEventType.DEATH,
            source=ObservationSource.CLIENT_LOG,
            character_id=char.character_id,
            payload={"character_name": "M6Hero"},
        )
    )

    # 8. Post-session recap generation
    entries = history_logger.read_history()
    recap = generate_session_recap(entries, session_id="m6_session_test")

    assert recap.session_id == "m6_session_test"
    assert recap.character_id == char.character_id
    assert recap.starting_level == 15
    assert recap.ending_level == 15
    assert recap.total_deaths == 1
    assert recap.total_events == 5
    assert recap.zones_visited == [combat_zone, hostile_zone_2, safe_zone]
