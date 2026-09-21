"""Unit tests for JourneyHistoryLogger and privacy verification."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from companion.observations.schema import (
    ObservationEvent,
    ObservationEventType,
    ObservationSource,
)
from companion.state.history import (
    JourneyHistoryEntry,
    JourneyHistoryLogger,
)


def test_journey_history_append_and_read(tmp_path: Path) -> None:
    history_file = tmp_path / "journey_history.jsonl"
    logger = JourneyHistoryLogger(history_file)

    ev1 = ObservationEvent.create(
        event_type=ObservationEventType.ZONE_TRANSITION,
        source=ObservationSource.CLIENT_LOG,
        character_id="hero_1",
        payload={"zone": "The Riverbank"},
    )
    ev2 = ObservationEvent.create(
        event_type=ObservationEventType.LEVEL_UP,
        source=ObservationSource.CLIENT_LOG,
        character_id="hero_1",
        payload={"level": 2},
    )

    logger.record_event(ev1)
    logger.record_event(ev2)

    entries = logger.read_history()
    assert len(entries) == 2
    assert entries[0].event_type == ObservationEventType.ZONE_TRANSITION.value
    assert entries[0].payload["zone"] == "The Riverbank"
    assert entries[1].event_type == ObservationEventType.LEVEL_UP.value
    assert entries[1].payload["level"] == 2


def test_journey_history_privacy_invariant(tmp_path: Path) -> None:
    history_file = tmp_path / "journey_history.jsonl"
    logger = JourneyHistoryLogger(history_file)

    # Record normalized event
    ev = ObservationEvent.create(
        event_type=ObservationEventType.ZONE_TRANSITION,
        source=ObservationSource.CLIENT_LOG,
        character_id="hero_1",
        payload={"zone": "Clear Fell"},
    )
    logger.record_event(ev)

    content = history_file.read_text(encoding="utf-8")
    for chat_prefix in ("@From", "@To", "$", "%"):
        assert chat_prefix not in content
