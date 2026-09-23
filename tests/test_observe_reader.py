"""Tests for IncrementalStreamReader in companion.observe.reader."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from companion.observe.manifest import ManifestManager, SessionManifest
from companion.observe.models import EvidencePriority, FactKind, ManifestStatus, ObservationEnvelope
from companion.observe.reader import (
    IncrementalStreamReader,
    ReaderState,
    ranges_from_set,
    set_from_ranges,
)


def _make_envelope(session_id: str, seq: int, event_type: str = "TEST_EVENT") -> ObservationEnvelope:
    return ObservationEnvelope(
        observation_session_id=session_id,
        sequence_number=seq,
        taxonomy=FactKind.OBSERVED_FACT,
        event_type=event_type,
        priority=EvidencePriority.MEDIUM,
        payload={"seq": seq},
    )


def test_ranges_from_set_and_set_from_ranges() -> None:
    s = {1, 2, 3, 5, 6, 8}
    r = ranges_from_set(s)
    assert r == [[1, 3], [5, 6], [8, 8]]
    assert set_from_ranges(r) == s
    assert ranges_from_set(set()) == []
    assert set_from_ranges([]) == set()


def test_partial_jsonl_line_boundary(tmp_path: Path) -> None:
    session_id = "test_session_partial"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True)

    events_file = session_dir / "events.jsonl"
    env1 = _make_envelope(session_id, 1)
    env2 = _make_envelope(session_id, 2)

    # Write complete line 1, then incomplete line 2 (no trailing newline)
    events_file.write_text(
        env1.model_dump_json() + "\n" + env2.model_dump_json()[:30],
        encoding="utf-8",
    )

    reader = IncrementalStreamReader(session_dir=session_dir, session_id=session_id)
    envelopes = reader.read_new_envelopes()

    assert len(envelopes) == 1
    assert envelopes[0].sequence_number == 1
    assert reader.contiguous_frontier == 1

    # Now complete line 2 with newline
    events_file.write_text(
        env1.model_dump_json() + "\n" + env2.model_dump_json() + "\n",
        encoding="utf-8",
    )

    envelopes2 = reader.read_new_envelopes()
    assert len(envelopes2) == 1
    assert envelopes2[0].sequence_number == 2
    assert reader.contiguous_frontier == 2


def test_stream_rotation_traversal(tmp_path: Path) -> None:
    session_id = "test_session_rotation"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True)

    seg0 = session_dir / "events.jsonl"
    seg1 = session_dir / "events.1.jsonl"

    env1 = _make_envelope(session_id, 1)
    env2 = _make_envelope(session_id, 2)
    seg0.write_text(env1.model_dump_json() + "\n", encoding="utf-8")
    seg1.write_text(env2.model_dump_json() + "\n", encoding="utf-8")

    reader = IncrementalStreamReader(session_dir=session_dir, session_id=session_id)
    envelopes = reader.read_new_envelopes()

    assert len(envelopes) == 2
    assert [e.sequence_number for e in envelopes] == [1, 2]
    assert reader.contiguous_frontier == 2
    assert reader.state.streams["events"].current_segment == "events.1.jsonl"


def test_missing_segment_gap_detection(tmp_path: Path) -> None:
    session_id = "test_session_gap"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True)

    seg0 = session_dir / "events.jsonl"
    seg2 = session_dir / "events.2.jsonl"  # segment 1 missing!

    env1 = _make_envelope(session_id, 1)
    env3 = _make_envelope(session_id, 3)
    seg0.write_text(env1.model_dump_json() + "\n", encoding="utf-8")
    seg2.write_text(env3.model_dump_json() + "\n", encoding="utf-8")

    reader = IncrementalStreamReader(session_dir=session_dir, session_id=session_id)
    envelopes = reader.read_new_envelopes()

    # Read segment 0, but detects segment 1 missing before segment 2
    assert len(envelopes) == 1
    assert envelopes[0].sequence_number == 1
    assert reader.contiguous_frontier == 1
    assert reader.gap_detected is True
    assert "ANALYST_STREAM_GAP" in (reader.gap_reason or "")


def test_duplicate_sequence_deduplicated(tmp_path: Path) -> None:
    session_id = "test_session_dupe"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True)

    events_file = session_dir / "events.jsonl"
    env1 = _make_envelope(session_id, 1)
    events_file.write_text(
        env1.model_dump_json() + "\n" + env1.model_dump_json() + "\n",
        encoding="utf-8",
    )

    reader = IncrementalStreamReader(session_dir=session_dir, session_id=session_id)
    envelopes = reader.read_new_envelopes()

    assert len(envelopes) == 1
    assert reader.contiguous_frontier == 1


def test_contiguous_frontier_advancement(tmp_path: Path) -> None:
    session_id = "test_session_frontier"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True)

    events_file = session_dir / "events.jsonl"
    deltas_file = session_dir / "state_deltas.jsonl"

    # Events stream has 1, 2, 4, 5
    for seq in [1, 2, 4, 5]:
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(_make_envelope(session_id, seq).model_dump_json() + "\n")

    reader = IncrementalStreamReader(session_dir=session_dir, session_id=session_id)
    envelopes = reader.read_new_envelopes()

    # Frontier holds at 2 because 3 is missing!
    assert reader.contiguous_frontier == 2
    assert reader.seen_ahead == {4, 5}

    # Now sequence 3 arrives in state_deltas
    with open(deltas_file, "a", encoding="utf-8") as f:
        f.write(_make_envelope(session_id, 3, "STATE_DELTA").model_dump_json() + "\n")

    envelopes2 = reader.read_new_envelopes()
    assert any(e.sequence_number == 3 for e in envelopes2)
    # Frontier advances through 5!
    assert reader.contiguous_frontier == 5
    assert len(reader.seen_ahead) == 0


def test_durable_drop_accounting(tmp_path: Path) -> None:
    session_id = "test_session_drop"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True)

    events_file = session_dir / "events.jsonl"
    for seq in [1, 2, 4, 5]:
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(_make_envelope(session_id, seq).model_dump_json() + "\n")

    # Sequence 3 was dropped by observer, recorded in manifest
    manifest = SessionManifest(
        session_id=session_id,
        runtime_run_id="run_1",
        started_at="2026-09-23T14:00:00Z",
        status=ManifestStatus.OPEN,
        sequence_high_watermark=5,
        persisted_event_count=4,
        dropped_event_count=1,
        dropped_sequence_ranges=[[3, 3]],
    )
    ManifestManager(session_dir / "session_manifest.json").save_atomic(manifest)

    reader = IncrementalStreamReader(session_dir=session_dir, session_id=session_id)
    envelopes = reader.read_new_envelopes()

    # Frontier advances through 5 because 3 is verified dropped!
    assert reader.contiguous_frontier == 5
    assert len(reader.seen_ahead) == 0


def test_read_ahead_saturation(tmp_path: Path) -> None:
    session_id = "test_session_sat"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True)

    events_file = session_dir / "events.jsonl"
    deltas_file = session_dir / "state_deltas.jsonl"

    # Sequence 1 in events
    with open(events_file, "a", encoding="utf-8") as f:
        f.write(_make_envelope(session_id, 1).model_dump_json() + "\n")

    # Sequence 2 missing! Sequences 3..8 in events
    for seq in range(3, 9):
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(_make_envelope(session_id, seq).model_dump_json() + "\n")

    # Reader with max_seen_ahead = 4
    reader = IncrementalStreamReader(
        session_dir=session_dir,
        session_id=session_id,
        max_seen_ahead=4,
    )
    envelopes = reader.read_new_envelopes()

    assert reader.contiguous_frontier == 1
    assert reader.read_ahead_saturated is True
    # Only 4 ahead sequences (3, 4, 5, 6) were buffered, 7 and 8 not consumed yet
    assert reader.seen_ahead == {3, 4, 5, 6}

    # Now sequence 2 arrives in deltas
    with open(deltas_file, "a", encoding="utf-8") as f:
        f.write(_make_envelope(session_id, 2, "STATE_DELTA").model_dump_json() + "\n")

    envelopes2 = reader.read_new_envelopes()
    # Missing sequence clears saturation and advances through 6, then reads 7 and 8
    assert reader.read_ahead_saturated is False
    assert reader.contiguous_frontier == 8
    assert len(reader.seen_ahead) == 0


def test_crash_recovery_with_ahead_ranges(tmp_path: Path) -> None:
    session_id = "test_session_crash_recovery"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True)

    events_file = session_dir / "events.jsonl"
    deltas_file = session_dir / "state_deltas.jsonl"

    # Events has 1, 2, 4, 5
    for seq in [1, 2, 4, 5]:
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(_make_envelope(session_id, seq).model_dump_json() + "\n")

    reader = IncrementalStreamReader(session_dir=session_dir, session_id=session_id)
    reader.read_new_envelopes()
    assert reader.contiguous_frontier == 2
    assert reader.seen_ahead == {4, 5}
    reader.save_state()

    # Verify state file saved accounted_ahead_ranges
    state_file = session_dir / "live_analysis" / "reader_state.json"
    assert state_file.exists()
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_data["contiguous_frontier"] == 2
    assert state_data["accounted_ahead_ranges"] == [[4, 5]]

    # Simulate restart by creating a new reader instance from disk
    reader_restart = IncrementalStreamReader(session_dir=session_dir, session_id=session_id)
    assert reader_restart.contiguous_frontier == 2
    assert reader_restart.seen_ahead == {4, 5}

    # No new envelopes if no files changed
    assert len(reader_restart.read_new_envelopes()) == 0

    # Write missing sequence 3 into deltas
    with open(deltas_file, "a", encoding="utf-8") as f:
        f.write(_make_envelope(session_id, 3, "STATE_DELTA").model_dump_json() + "\n")

    new_envs = reader_restart.read_new_envelopes()
    assert len(new_envs) == 1
    assert new_envs[0].sequence_number == 3
    # Contiguous frontier advances to 5!
    assert reader_restart.contiguous_frontier == 5
    assert len(reader_restart.seen_ahead) == 0
