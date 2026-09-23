"""Comprehensive integration verification for real-time development observation review."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest

from companion.observe.analyst import LocalLiveAnalyst
from companion.observe.cursor import (
    ReaderCursorManager,
    ReviewCursorManager,
    compute_reader_lag,
    compute_review_lag,
)
from companion.observe.journal import (
    FindingOperation,
    FindingStatus,
    HermesFinding,
    ReviewBatchResult,
    ReviewJournalManager,
    compute_finding_id,
    compute_review_batch_id,
)
from companion.observe.manifest import ManifestManager, SessionManifest
from companion.observe.models import (
    EvidencePriority,
    FactKind,
    HealthState,
    ManifestStatus,
    ObservationEnvelope,
)
from companion.observe.reader import IncrementalStreamReader


def _make_env(session_id: str, seq: int, event_type: str = "EVENT", payload: dict | None = None) -> ObservationEnvelope:
    return ObservationEnvelope(
        observation_session_id=session_id,
        sequence_number=seq,
        taxonomy=FactKind.OBSERVED_FACT,
        event_type=event_type,
        priority=EvidencePriority.MEDIUM,
        payload=payload or {"seq": seq},
    )


# ---------------------------------------------------------------------------
# 1. Reader Crash Safety & Saturation Invariants
# ---------------------------------------------------------------------------


def test_reader_crash_safety_and_ahead_reconstruction(tmp_path: Path) -> None:
    session_id = "obs_int_crash_ahead"
    sdir = tmp_path / session_id
    sdir.mkdir(parents=True)

    events_file = sdir / "events.jsonl"
    deltas_file = sdir / "state_deltas.jsonl"

    # Stream A (events) has sequences 1, 2, 4, 5, 6
    for seq in [1, 2, 4, 5, 6]:
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(_make_env(session_id, seq).model_dump_json() + "\n")

    reader = IncrementalStreamReader(session_dir=sdir, session_id=session_id)
    reader.read_new_envelopes()

    # Contiguous frontier holds at 2 (seq 3 missing)
    assert reader.contiguous_frontier == 2
    assert reader.seen_ahead == {4, 5, 6}
    reader.save_state()

    # Crash & restart: state reconstructs from reader_state.json
    restarted = IncrementalStreamReader(session_dir=sdir, session_id=session_id)
    assert restarted.contiguous_frontier == 2
    assert restarted.seen_ahead == {4, 5, 6}

    # Missing sequence 3 arrives on Stream B (deltas)
    with open(deltas_file, "a", encoding="utf-8") as f:
        f.write(_make_env(session_id, 3, "STATE_DELTA").model_dump_json() + "\n")

    new_envs = restarted.read_new_envelopes()
    assert len(new_envs) == 1
    assert new_envs[0].sequence_number == 3
    # Contiguous frontier advances through all retained ahead evidence to 6!
    assert restarted.contiguous_frontier == 6
    assert len(restarted.seen_ahead) == 0


def test_reader_saturation_bounded_capacity_and_recovery(tmp_path: Path) -> None:
    session_id = "obs_int_saturation"
    sdir = tmp_path / session_id
    sdir.mkdir(parents=True)

    events_file = sdir / "events.jsonl"
    deltas_file = sdir / "state_deltas.jsonl"

    # Seq 1 arrives
    with open(events_file, "a", encoding="utf-8") as f:
        f.write(_make_env(session_id, 1).model_dump_json() + "\n")

    # Sequence 2 missing. Sequences 3..10 arrive on events
    for seq in range(3, 11):
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(_make_env(session_id, seq).model_dump_json() + "\n")

    # Reader with max_seen_ahead = 5
    reader = IncrementalStreamReader(session_dir=sdir, session_id=session_id, max_seen_ahead=5)
    reader.read_new_envelopes()

    assert reader.contiguous_frontier == 1
    assert reader.read_ahead_saturated is True
    # Exactly 5 ahead sequences buffered (3, 4, 5, 6, 7); 8, 9, 10 not yet consumed
    assert reader.seen_ahead == {3, 4, 5, 6, 7}

    # Missing sequence 2 arrives
    with open(deltas_file, "a", encoding="utf-8") as f:
        f.write(_make_env(session_id, 2, "STATE_DELTA").model_dump_json() + "\n")

    reader.read_new_envelopes()
    # Saturation cleared, frontier advances through 7 then consumes remaining 8..10
    assert reader.read_ahead_saturated is False
    assert reader.contiguous_frontier == 10
    assert len(reader.seen_ahead) == 0


# ---------------------------------------------------------------------------
# 2. Review Batch Idempotency & Crash Consistency Cases (A, B, C, D)
# ---------------------------------------------------------------------------


def test_review_crash_case_a_provider_fails_before_durable_result(tmp_path: Path) -> None:
    session_id = "obs_case_a"
    sdir = tmp_path / session_id
    cursor_mgr = ReviewCursorManager(
        cursor_path=sdir / "live_analysis" / "hermes_review_cursor.json",
        session_id=session_id,
    )

    # Sequence 1..10 needs review, but AI provider fails mid-call
    # Result: no batch result written to disk, review cursor remains at 0
    assert cursor_mgr.review_contiguous_frontier == 0
    cursor_mgr.save_atomic()

    reloaded = ReviewCursorManager(
        cursor_path=sdir / "live_analysis" / "hermes_review_cursor.json",
        session_id=session_id,
    )
    assert reloaded.review_contiguous_frontier == 0


def test_review_crash_case_b_batch_persisted_crash_before_findings(tmp_path: Path) -> None:
    session_id = "obs_case_b"
    sdir = tmp_path / session_id
    journal = ReviewJournalManager(session_dir=sdir, session_id=session_id)
    cursor_mgr = ReviewCursorManager(
        cursor_path=sdir / "live_analysis" / "hermes_review_cursor.json",
        session_id=session_id,
    )

    batch_id = compute_review_batch_id(session_id, 1, 20, ["evt_1"])
    finding_id = compute_finding_id(session_id, "notification", "drop")
    op = FindingOperation(
        op="CREATE",
        finding_id=finding_id,
        category="notification",
        semantic_issue_key="drop",
        status=FindingStatus.WATCHING,
        title="Dropped notification under load",
        summary="Queue was full",
        occurrence_count_delta=1,
        new_evidence_ids=["evt_1"],
    )
    result = ReviewBatchResult(
        review_batch_id=batch_id,
        session_id=session_id,
        sequence_start=1,
        sequence_end=20,
        reviewed_evidence_ids=["evt_1"],
        operations=[op],
        review_status="COMPLETED",
    )

    # Durable batch result persisted, but crash occurs before findings or cursor updated
    journal.save_batch_result(result)
    assert len(journal.get_findings()) == 0
    assert cursor_mgr.review_contiguous_frontier == 0

    # Resume: detects existing batch result, skips AI call, applies operations, advances cursor
    existing_result = journal.load_batch_result(batch_id)
    assert existing_result is not None
    journal.apply_batch_result(existing_result)
    cursor_mgr.record_batch_reviewed(batch_id, existing_result.sequence_start, existing_result.sequence_end)
    cursor_mgr.save_atomic()

    assert len(journal.get_findings()) == 1
    assert cursor_mgr.review_contiguous_frontier == 20


def test_review_crash_case_c_findings_persisted_crash_before_cursor(tmp_path: Path) -> None:
    session_id = "obs_case_c"
    sdir = tmp_path / session_id
    journal = ReviewJournalManager(session_dir=sdir, session_id=session_id)
    cursor_mgr = ReviewCursorManager(
        cursor_path=sdir / "live_analysis" / "hermes_review_cursor.json",
        session_id=session_id,
    )

    batch_id = compute_review_batch_id(session_id, 1, 15, ["evt_5"])
    finding_id = compute_finding_id(session_id, "objective", "churn:boss")
    op = FindingOperation(
        op="CREATE",
        finding_id=finding_id,
        category="objective",
        semantic_issue_key="churn:boss",
        status=FindingStatus.WATCHING,
        title="Boss objective churn",
        summary="Flapping objective",
        occurrence_count_delta=1,
        new_evidence_ids=["evt_5"],
    )
    result = ReviewBatchResult(
        review_batch_id=batch_id,
        session_id=session_id,
        sequence_start=1,
        sequence_end=15,
        reviewed_evidence_ids=["evt_5"],
        operations=[op],
        review_status="COMPLETED",
    )

    journal.save_batch_result(result)
    journal.apply_batch_result(result)
    # Crash occurs before cursor_mgr.record_batch_reviewed / save_atomic
    assert cursor_mgr.review_contiguous_frontier == 0

    # Replay on resume: applies batch result again
    journal.apply_batch_result(result)
    cursor_mgr.record_batch_reviewed(batch_id, result.sequence_start, result.sequence_end)
    cursor_mgr.save_atomic()

    findings = journal.get_findings()
    assert len(findings) == 1
    assert findings[0].revision == 1
    assert findings[0].occurrence_count == 1
    assert cursor_mgr.review_contiguous_frontier == 15


def test_review_crash_case_d_no_finding_batch_advances_cursor(tmp_path: Path) -> None:
    session_id = "obs_case_d"
    sdir = tmp_path / session_id
    journal = ReviewJournalManager(session_dir=sdir, session_id=session_id)
    cursor_mgr = ReviewCursorManager(
        cursor_path=sdir / "live_analysis" / "hermes_review_cursor.json",
        session_id=session_id,
    )

    batch_id = compute_review_batch_id(session_id, 1, 50, ["evt_10"])
    result = ReviewBatchResult(
        review_batch_id=batch_id,
        session_id=session_id,
        sequence_start=1,
        sequence_end=50,
        reviewed_evidence_ids=["evt_10"],
        operations=[],
        review_status="COMPLETED",
    )

    journal.save_batch_result(result)
    journal.apply_batch_result(result)
    cursor_mgr.record_batch_reviewed(batch_id, result.sequence_start, result.sequence_end)
    cursor_mgr.save_atomic()

    assert cursor_mgr.review_contiguous_frontier == 50
    assert len(journal.get_findings()) == 0


# ---------------------------------------------------------------------------
# 3. Finding Identity Stability & Lifecycle Evolution
# ---------------------------------------------------------------------------


def test_finding_identity_stability_across_revisions(tmp_path: Path) -> None:
    session_id = "obs_finding_stability"
    sdir = tmp_path / session_id
    journal = ReviewJournalManager(session_dir=sdir, session_id=session_id)

    finding_id = compute_finding_id(session_id, "anomaly", "pattern_0x42")

    # Revision 1: WATCHING
    b1 = compute_review_batch_id(session_id, 1, 10, ["evt_1"])
    res1 = ReviewBatchResult(
        review_batch_id=b1,
        session_id=session_id,
        sequence_start=1,
        sequence_end=10,
        reviewed_evidence_ids=["evt_1"],
        operations=[
            FindingOperation(
                op="CREATE",
                finding_id=finding_id,
                category="anomaly",
                semantic_issue_key="pattern_0x42",
                status=FindingStatus.WATCHING,
                title="Pattern 0x42 observed",
                summary="First occurrence",
                occurrence_count_delta=1,
                new_evidence_ids=["evt_1"],
            )
        ],
    )
    journal.apply_batch_result(res1)

    # Revision 2: Evolves to CORROBORATED
    b2 = compute_review_batch_id(session_id, 11, 20, ["evt_2", "mrk_9"])
    res2 = ReviewBatchResult(
        review_batch_id=b2,
        session_id=session_id,
        sequence_start=11,
        sequence_end=20,
        reviewed_evidence_ids=["evt_2", "mrk_9"],
        operations=[
            FindingOperation(
                op="UPDATE",
                finding_id=finding_id,
                category="anomaly",
                semantic_issue_key="pattern_0x42",
                status=FindingStatus.CORROBORATED,
                title="Pattern 0x42 observed",
                summary="Corroborated by user marker",
                occurrence_count_delta=1,
                new_evidence_ids=["evt_2", "mrk_9"],
                corroboration_note="Player marker confirmed glitch",
            )
        ],
    )
    findings = journal.apply_batch_result(res2)
    assert len(findings) == 1
    f = findings[0]
    assert f.finding_id == finding_id
    assert f.status == FindingStatus.CORROBORATED
    assert f.revision == 2
    assert f.occurrence_count == 2
    assert f.evidence_refs == ["evt_1", "evt_2", "mrk_9"]


# ---------------------------------------------------------------------------
# 4. Contiguous Frontier vs Max-Seen Sequence
# ---------------------------------------------------------------------------


def test_contiguous_frontier_gap_semantics(tmp_path: Path) -> None:
    session_id = "obs_gap_frontier"
    sdir = tmp_path / session_id
    sdir.mkdir(parents=True)

    events_file = sdir / "events.jsonl"
    for seq in [1, 2, 4, 5]:
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(_make_env(session_id, seq).model_dump_json() + "\n")

    reader = IncrementalStreamReader(session_dir=sdir, session_id=session_id)
    reader.read_new_envelopes()

    # Contiguous frontier must hold at 2, NOT 5
    assert reader.contiguous_frontier == 2

    # Sequence 3 accounted via manifest drop
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
    ManifestManager(sdir / "session_manifest.json").save_atomic(manifest)

    reader.read_new_envelopes()
    # Verified dropped sequence 3 advances frontier to 5!
    assert reader.contiguous_frontier == 5


# ---------------------------------------------------------------------------
# 5. Review Frontier Progression & Contiguous Lag Calculations
# ---------------------------------------------------------------------------


def test_review_frontier_and_contiguous_lag(tmp_path: Path) -> None:
    session_id = "obs_lag"
    sdir = tmp_path / session_id
    cursor_mgr = ReviewCursorManager(
        cursor_path=sdir / "live_analysis" / "hermes_review_cursor.json",
        session_id=session_id,
    )

    # Batches 1..100 and 102..120 completed, 101 pending
    cursor_mgr.record_batch_reviewed("rb_1", 1, 100)
    cursor_mgr.record_batch_reviewed("rb_2", 102, 120)

    # Frontier MUST hold at 100
    assert cursor_mgr.review_contiguous_frontier == 100
    assert cursor_mgr.accounted_reviewed_ranges == [[102, 120]]

    # Observer at 150, Reader at 130, Review at 100
    reader_lag = compute_reader_lag(150, 130)
    review_lag = compute_review_lag(130, 100)
    assert reader_lag == 20
    assert review_lag == 30

    # Sequence 101 completes
    cursor_mgr.record_batch_reviewed("rb_3", 101, 101)
    assert cursor_mgr.review_contiguous_frontier == 120
    assert cursor_mgr.accounted_reviewed_ranges == []

    # Updated review lag
    review_lag_updated = compute_review_lag(130, 120)
    assert review_lag_updated == 10
