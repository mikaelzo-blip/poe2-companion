"""Tests for LocalLiveAnalyst in companion.observe.analyst."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from companion.observe.analyst import (
    LocalLiveAnalyst,
    LocalSignal,
    compute_local_signal_id,
)
from companion.observe.models import (
    EvidencePriority,
    FactKind,
    ObservationEnvelope,
    UserMarkerRecord,
)


def _make_envelope(
    session_id: str,
    seq: int,
    event_type: str = "TEST_EVENT",
    payload: dict | None = None,
) -> ObservationEnvelope:
    return ObservationEnvelope(
        observation_session_id=session_id,
        sequence_number=seq,
        taxonomy=FactKind.OBSERVED_FACT,
        event_type=event_type,
        priority=EvidencePriority.MEDIUM,
        payload=payload or {"seq": seq},
    )


def test_deterministic_local_signal_id() -> None:
    session_id = "obs_123"
    sig_id1 = compute_local_signal_id(session_id, "UNKNOWN_PERSISTENCE", ["evt_1", "evt_2"])
    sig_id2 = compute_local_signal_id(session_id, "UNKNOWN_PERSISTENCE", ["evt_2", "evt_1"])
    assert sig_id1 == sig_id2
    assert sig_id1.startswith("sig:obs_123:UNKNOWN_PERSISTENCE:")


def test_factual_signals_generated_without_speculative_labels(tmp_path: Path) -> None:
    session_id = "test_session_analyst"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True)

    events_file = session_dir / "events.jsonl"
    deltas_file = session_dir / "state_deltas.jsonl"
    objectives_file = session_dir / "objective_traces.jsonl"
    markers_file = session_dir / "markers.jsonl"

    # Write unknown delta
    env1 = _make_envelope(
        session_id,
        1,
        "STATE_DELTA",
        {"field": "life_total", "before": 100, "after": None, "verification_status": "UNKNOWN"},
    )
    deltas_file.write_text(env1.model_dump_json() + "\n", encoding="utf-8")

    # Write objective churn (same objective reevaluated repeatedly)
    env2 = _make_envelope(
        session_id,
        2,
        "OBJECTIVE_TRACE",
        {"selected_objective_id": "quest:fetid_pool", "objective_changed": False},
    )
    objectives_file.write_text(env2.model_dump_json() + "\n", encoding="utf-8")

    # Write user marker
    env3 = _make_envelope(
        session_id,
        3,
        "USER_MARKER",
        {"marker_id": "mrk_1", "note": "boss fight glitch"},
    )
    markers_file.write_text(env3.model_dump_json() + "\n", encoding="utf-8")

    analyst = LocalLiveAnalyst(session_dir=session_dir, session_id=session_id)
    signals = analyst.step()

    assert len(signals) >= 2
    signal_types = {s.signal_type for s in signals}
    assert "USER_MARKER_DETECTED" in signal_types

    # Assert local signals never contain speculative defect claims
    for s in signals:
        assert "LIKELY_DEFECT" not in s.signal_type
        assert "FEATURE_OPPORTUNITY" not in s.signal_type
        assert s.signal_id.startswith(f"sig:{session_id}:")

    # Verify signals persisted to local_signals.jsonl
    signals_file = session_dir / "live_analysis" / "local_signals.jsonl"
    assert signals_file.exists()
    persisted_lines = [
        json.loads(line) for line in signals_file.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(persisted_lines) == len(signals)


def test_replay_deduplication(tmp_path: Path) -> None:
    session_id = "test_session_dedupe"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True)

    markers_file = session_dir / "markers.jsonl"
    env1 = _make_envelope(
        session_id,
        1,
        "USER_MARKER",
        {"marker_id": "mrk_1", "note": "freeze test"},
    )
    markers_file.write_text(env1.model_dump_json() + "\n", encoding="utf-8")

    analyst = LocalLiveAnalyst(session_dir=session_dir, session_id=session_id)
    signals1 = analyst.step()
    assert len(signals1) == 1

    # Simulate crash before reader cursor saved, but after signals written
    # Reset reader cursor to 0 to simulate replaying the same record
    reader_state_file = session_dir / "live_analysis" / "reader_state.json"
    if reader_state_file.exists():
        reader_state_file.unlink()

    analyst_replay = LocalLiveAnalyst(session_dir=session_dir, session_id=session_id)
    signals2 = analyst_replay.step()

    # Replayed signals must have the identical signal_id and not duplicate entries in local_signals.jsonl
    assert len(signals2) == 1
    assert signals2[0].signal_id == signals1[0].signal_id

    signals_file = session_dir / "live_analysis" / "local_signals.jsonl"
    persisted = [
        json.loads(line) for line in signals_file.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    # No duplicate lines in file
    persisted_ids = [p["signal_id"] for p in persisted]
    assert len(persisted_ids) == 1
    assert persisted_ids[0] == signals1[0].signal_id


def test_marker_offline_queueing_and_escalation(tmp_path: Path) -> None:
    session_id = "test_session_offline_marker"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True)

    markers_file = session_dir / "markers.jsonl"
    env1 = _make_envelope(
        session_id,
        1,
        "USER_MARKER",
        {"marker_id": "mrk_offline", "note": "offline marker note"},
    )
    markers_file.write_text(env1.model_dump_json() + "\n", encoding="utf-8")

    analyst = LocalLiveAnalyst(session_dir=session_dir, session_id=session_id)
    analyst.step()

    # Marker must be tracked in pending_marker_ids
    assert "mrk_offline" in analyst.reader.pending_marker_ids
    reader_state = analyst.reader.state
    assert "mrk_offline" in reader_state.pending_marker_ids


def test_privacy_redaction_in_signals(tmp_path: Path) -> None:
    session_id = "test_session_privacy"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True)

    events_file = session_dir / "events.jsonl"
    env1 = _make_envelope(
        session_id,
        1,
        "LOG_ANOMALY",
        {
            "line": "@From Alice: whisper text secret_password123",
            "pattern_hash": "abc",
            "classification": "UNKNOWN",
        },
    )
    events_file.write_text(env1.model_dump_json() + "\n", encoding="utf-8")

    analyst = LocalLiveAnalyst(session_dir=session_dir, session_id=session_id)
    signals = analyst.step()

    for s in signals:
        dumped = json.dumps(s.model_dump())
        assert "secret_password123" not in dumped
        assert "@From Alice" not in dumped
