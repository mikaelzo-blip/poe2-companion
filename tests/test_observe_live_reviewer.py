"""Tests for LiveReviewEngine and review heartbeat telemetry in companion.observe.live_reviewer."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest

from companion.observe.cursor import ReviewCursorManager
from companion.observe.journal import FindingStatus, ReviewJournalManager
from companion.observe.live_reviewer import (
    HermesReviewStatus,
    HermesReviewStatusManager,
    LiveReviewEngine,
)
from companion.observe.manifest import ManifestManager, SessionManifest
from companion.observe.models import (
    EvidencePriority,
    FactKind,
    HealthState,
    ManifestStatus,
    ObservationEnvelope,
)


def _setup_session(base_dir: Path, session_id: str) -> Path:
    sdir = base_dir / session_id
    sdir.mkdir(parents=True)

    manifest = SessionManifest(
        session_id=session_id,
        runtime_run_id="run_test",
        started_at="2026-09-23T14:00:00Z",
        status=ManifestStatus.OPEN,
        sequence_high_watermark=20,
        persisted_event_count=20,
        health_state=HealthState.HEALTHY,
    )
    ManifestManager(sdir / "session_manifest.json").save_atomic(manifest)

    # Stream with marker at sequence 5
    events_file = sdir / "events.jsonl"
    markers_file = sdir / "markers.jsonl"

    for seq in range(1, 21):
        if seq == 5:
            env = ObservationEnvelope(
                observation_session_id=session_id,
                sequence_number=5,
                taxonomy=FactKind.OBSERVED_FACT,
                event_type="USER_MARKER",
                priority=EvidencePriority.HIGH,
                payload={"marker_id": "mrk_boss", "note": "boss attack delay glitch"},
            )
            with open(markers_file, "a", encoding="utf-8") as f:
                f.write(env.model_dump_json() + "\n")
        else:
            env = ObservationEnvelope(
                observation_session_id=session_id,
                sequence_number=seq,
                taxonomy=FactKind.OBSERVED_FACT,
                event_type="TEST_EVENT",
                priority=EvidencePriority.MEDIUM,
                payload={"seq": seq},
            )
            with open(events_file, "a", encoding="utf-8") as f:
                f.write(env.model_dump_json() + "\n")

    return sdir


def test_heartbeat_status_manager(tmp_path: Path) -> None:
    status_file = tmp_path / "hermes_review_status.json"
    mgr = HermesReviewStatusManager(status_file)

    assert mgr.load() is None
    status = mgr.update_heartbeat("run_1", 50, state="ACTIVE")
    assert status.state == "ACTIVE"
    assert status.last_reviewed_sequence == 50
    assert status_file.exists()

    loaded = mgr.load()
    assert loaded is not None
    assert loaded.review_run_id == "run_1"
    assert loaded.state == "ACTIVE"


def test_live_review_engine_step_and_marker_prioritization(tmp_path: Path) -> None:
    session_id = "obs_engine_test"
    sdir = _setup_session(tmp_path, session_id)

    engine = LiveReviewEngine(session_dir=sdir, session_id=session_id, batch_size=10)
    batch_result = engine.step_review()

    assert batch_result is not None
    assert batch_result.sequence_start == 1
    assert batch_result.sequence_end == 10
    assert batch_result.review_status == "COMPLETED"

    # Batch 1 contains marker at seq 5 -> finding generated
    journal = ReviewJournalManager(session_dir=sdir, session_id=session_id)
    findings = journal.get_findings()
    assert len(findings) == 1
    assert "mrk_boss" in findings[0].semantic_issue_key or "boss" in findings[0].title

    # Review cursor must have advanced to 10
    cursor_mgr = ReviewCursorManager(
        cursor_path=sdir / "live_analysis" / "hermes_review_cursor.json",
        session_id=session_id,
    )
    assert cursor_mgr.review_contiguous_frontier == 10

    # Heartbeat file updated
    status_mgr = HermesReviewStatusManager(sdir / "live_analysis" / "hermes_review_status.json")
    st = status_mgr.load()
    assert st is not None
    assert st.state == "ACTIVE"
    assert st.last_reviewed_sequence == 10

    # Step again for remaining 11..20 (no marker, clean batch)
    batch_result2 = engine.step_review()
    assert batch_result2 is not None
    assert batch_result2.sequence_start == 11
    assert batch_result2.sequence_end == 20
    assert cursor_mgr.load().review_contiguous_frontier == 20

    # Step again: no more pending evidence -> returns None
    assert engine.step_review() is None
