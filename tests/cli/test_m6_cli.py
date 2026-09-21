"""Unit and integration tests for M6 CLI subcommands: notify and session recap."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from companion.cli import main
from companion.observations.schema import ObservationEvent, ObservationEventType, ObservationSource
from companion.state.history import JourneyHistoryLogger


def test_notify_test_cli_delivered(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([
        "notify", "test",
        "--title", "Urgent Danger",
        "--message", "Low HP",
        "--severity", "CRITICAL",
        "--zone", "The Grim Tangle",
        "--json",
    ])
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["status"] == "DELIVERED"
    assert data["payload"]["title"] == "Urgent Danger"


def test_notify_test_cli_queued_in_combat(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([
        "notify", "test",
        "--title", "Gem Suggestion",
        "--message", "Check support gems",
        "--severity", "INFO",
        "--zone", "The Grim Tangle",
        "--json",
    ])
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["status"] == "QUEUED"


def test_session_recap_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True)
    logger = JourneyHistoryLogger(runtime_dir / "journey_history.jsonl")

    logger.record_event(
        ObservationEvent.create(
            event_type=ObservationEventType.ZONE_TRANSITION,
            source=ObservationSource.CLIENT_LOG,
            character_id="hero_test",
            payload={"zone": "The Clear Fell Encampment"},
        )
    )
    logger.record_event(
        ObservationEvent.create(
            event_type=ObservationEventType.LEVEL_UP,
            source=ObservationSource.CLIENT_LOG,
            character_id="hero_test",
            payload={"character_name": "Hero", "level": 10},
        )
    )

    exit_code = main([
        "session", "recap",
        "--runtime", str(runtime_dir),
        "--session-id", "test_recap_session",
        "--json",
    ])
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["session_id"] == "test_recap_session"
    assert data["character_id"] == "hero_test"
    assert data["total_events"] == 2
    assert data["zones_visited"] == ["The Clear Fell Encampment"]
