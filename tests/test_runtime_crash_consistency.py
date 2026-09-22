"""Unit tests for crash consistency, stable source stream identities, and history deduplication."""

from __future__ import annotations

from pathlib import Path
import pytest

from companion.observations.schema import ObservationEvent, ObservationEventType, ObservationSource
from companion.runtime.normalizer import build_observation_id, build_source_stream_id, normalize_log_event
from companion.sensing.client_log import ParsedLogEvent, ParsedLogEventType
from companion.state.history import JourneyHistoryLogger


def test_stable_source_stream_id() -> None:
    stream_id_1 = build_source_stream_id(prefix_hash="abcdef1234567890", stream_epoch=1)
    stream_id_2 = build_source_stream_id(prefix_hash="abcdef1234567890", stream_epoch=2)
    assert stream_id_1 == "abcdef1234567890:epoch_1"
    assert stream_id_2 == "abcdef1234567890:epoch_2"
    assert stream_id_1 != stream_id_2


def test_build_observation_id_deterministic() -> None:
    obs_id = build_observation_id(
        source_stream_id="stream1:epoch_1",
        start_offset=100,
        end_offset=250,
        event_type="zone_transition",
    )
    assert obs_id == "stream1:epoch_1:100:250:zone_transition"


def test_truncation_produces_distinct_observation_ids_at_same_offset() -> None:
    obs_id_epoch1 = build_observation_id(
        source_stream_id=build_source_stream_id("fp1", 1),
        start_offset=0,
        end_offset=100,
        event_type="zone_transition",
    )
    obs_id_epoch2 = build_observation_id(
        source_stream_id=build_source_stream_id("fp1", 2),
        start_offset=0,
        end_offset=100,
        event_type="zone_transition",
    )
    assert obs_id_epoch1 != obs_id_epoch2


def test_normalize_log_event() -> None:
    parsed = ParsedLogEvent(
        event_type=ParsedLogEventType.ZONE_ENTER,
        payload={"zone": "The Coast"},
    )
    obs = normalize_log_event(
        parsed_event=parsed,
        source_stream_id="stream1:epoch_1",
        start_offset=50,
        end_offset=120,
        character_id="Witch",
    )
    assert obs.event_id == "stream1:epoch_1:50:120:zone_transition"
    assert obs.event_type == ObservationEventType.ZONE_TRANSITION
    assert obs.source == ObservationSource.CLIENT_LOG
    assert obs.payload["zone"] == "The Coast"
    assert obs.payload["start_offset"] == 50
    assert obs.payload["end_offset"] == 120
    assert obs.payload["source_stream_id"] == "stream1:epoch_1"


def test_journey_history_deduplication_on_replay(tmp_path: Path) -> None:
    history_file = tmp_path / "journey_history.jsonl"
    logger = JourneyHistoryLogger(history_file)

    parsed = ParsedLogEvent(
        event_type=ParsedLogEventType.LEVEL_UP,
        payload={"character_name": "Witch", "level": 2},
    )
    obs = normalize_log_event(
        parsed_event=parsed,
        source_stream_id="stream1:epoch_1",
        start_offset=100,
        end_offset=200,
        character_id="Witch",
    )

    # First write
    entry1 = logger.record_event(obs)
    # Replay identical event (e.g. after crash before checkpoint)
    entry2 = logger.record_event(obs)

    assert entry1.entry_id == obs.event_id
    assert entry2.entry_id == obs.event_id

    # Must contain only ONE entry in file
    entries = logger.read_history()
    assert len(entries) == 1
    assert entries[0].entry_id == obs.event_id

    # A distinct event at a different offset is recorded
    obs_next = normalize_log_event(
        parsed_event=parsed,
        source_stream_id="stream1:epoch_1",
        start_offset=200,
        end_offset=300,
        character_id="Witch",
    )
    logger.record_event(obs_next)
    entries_after = logger.read_history()
    assert len(entries_after) == 2
