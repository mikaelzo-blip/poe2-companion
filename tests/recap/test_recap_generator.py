"""Unit tests for session recap generation and formatting."""

from __future__ import annotations

import json
import pytest

from companion.recap.generator import (
    format_recap_json,
    format_recap_text,
    generate_session_recap,
)
from companion.recap.schema import SessionRecap
from companion.state.history import JourneyHistoryEntry


def test_generate_session_recap_empty() -> None:
    recap = generate_session_recap([], session_id="test_empty")
    assert recap.session_id == "test_empty"
    assert recap.levels_gained == 0
    assert recap.total_deaths == 0
    assert recap.total_events == 0
    assert len(recap.zones_visited) == 0

    text = format_recap_text(recap)
    assert "Session Recap [test_empty]" in text
    assert "Levels Gained: 0" in text


def test_generate_session_recap_with_events() -> None:
    entries = [
        JourneyHistoryEntry(
            entry_id="e1",
            timestamp="2026-09-22T10:00:00+00:00",
            character_id="hero_1",
            event_type="zone_transition",
            source="client_log",
            payload={"zone": "The Clear Fell Encampment"},
        ),
        JourneyHistoryEntry(
            entry_id="e2",
            timestamp="2026-09-22T10:05:00+00:00",
            character_id="hero_1",
            event_type="zone_transition",
            source="client_log",
            payload={"zone": "The Riverbank"},
        ),
        JourneyHistoryEntry(
            entry_id="e3",
            timestamp="2026-09-22T10:15:00+00:00",
            character_id="hero_1",
            event_type="level_up",
            source="client_log",
            payload={"character_name": "Hero", "level": 14},
        ),
        JourneyHistoryEntry(
            entry_id="e4",
            timestamp="2026-09-22T10:25:00+00:00",
            character_id="hero_1",
            event_type="level_up",
            source="client_log",
            payload={"character_name": "Hero", "level": 15},
        ),
        JourneyHistoryEntry(
            entry_id="e5",
            timestamp="2026-09-22T10:30:00+00:00",
            character_id="hero_1",
            event_type="death",
            source="client_log",
            payload={"character_name": "Hero"},
        ),
    ]

    recap = generate_session_recap(entries, session_id="sess_42")
    assert recap.session_id == "sess_42"
    assert recap.character_id == "hero_1"
    assert recap.total_events == 5
    assert recap.starting_level == 14
    assert recap.ending_level == 15
    assert recap.levels_gained == 1
    assert recap.total_deaths == 1
    assert recap.zones_visited == ["The Clear Fell Encampment", "The Riverbank"]

    json_str = format_recap_json(recap)
    data = json.loads(json_str)
    assert data["session_id"] == "sess_42"
    assert data["total_deaths"] == 1

    text = format_recap_text(recap)
    assert "Levels Gained: 1 (14 -> 15)" in text
    assert "Deaths: 1" in text
    assert "Zones Visited (2):" in text
