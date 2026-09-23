"""Tests for ReviewJournalManager and Hermes finding models in companion.observe.journal."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from companion.observe.cursor import ReviewCursorManager
from companion.observe.journal import (
    FindingOperation,
    FindingStatus,
    HermesFinding,
    ReviewBatchResult,
    ReviewJournalManager,
    compute_finding_id,
    compute_review_batch_id,
)


def test_deterministic_review_batch_id() -> None:
    session_id = "obs_20260923_120000"
    id1 = compute_review_batch_id(session_id, 1, 100, ["evt_2", "evt_1", "evt_3"])
    id2 = compute_review_batch_id(session_id, 1, 100, ["evt_1", "evt_3", "evt_2"])
    assert id1 == id2
    assert id1.startswith("rb_")


def test_stable_finding_identity() -> None:
    session_id = "obs_test_finding"
    f_id = compute_finding_id(session_id, "notification", "late-delivery:zone_entry")
    assert f_id == f"find:{session_id}:notification:late-delivery:zone_entry"


def test_batch_result_atomic_save_and_load(tmp_path: Path) -> None:
    session_id = "obs_save_load"
    session_dir = tmp_path / session_id
    journal = ReviewJournalManager(session_dir=session_dir, session_id=session_id)

    batch_id = compute_review_batch_id(session_id, 1, 10, ["evt_1"])
    op = FindingOperation(
        op="CREATE",
        finding_id=compute_finding_id(session_id, "unknown", "life_total"),
        category="unknown",
        semantic_issue_key="life_total",
        status=FindingStatus.WATCHING,
        title="Unknown life total on zone change",
        summary="Life total was null after zone transition",
        occurrence_count_delta=1,
        new_evidence_ids=["evt_1"],
    )
    result = ReviewBatchResult(
        review_batch_id=batch_id,
        session_id=session_id,
        sequence_start=1,
        sequence_end=10,
        reviewed_evidence_ids=["evt_1"],
        operations=[op],
        review_status="COMPLETED",
    )

    journal.save_batch_result(result)
    batch_file = session_dir / "live_analysis" / "review_batches" / f"{batch_id}.json"
    assert batch_file.exists()

    loaded = journal.load_batch_result(batch_id)
    assert loaded is not None
    assert loaded.review_batch_id == batch_id
    assert len(loaded.operations) == 1
    assert loaded.operations[0].finding_id == op.finding_id


def test_finding_revision_idempotency(tmp_path: Path) -> None:
    session_id = "obs_idempotency"
    session_dir = tmp_path / session_id
    journal = ReviewJournalManager(session_dir=session_dir, session_id=session_id)

    batch_id = compute_review_batch_id(session_id, 1, 20, ["evt_1", "evt_2"])
    finding_id = compute_finding_id(session_id, "parser", "unrecognized_debug")
    op = FindingOperation(
        op="CREATE",
        finding_id=finding_id,
        category="parser",
        semantic_issue_key="unrecognized_debug",
        status=FindingStatus.POSSIBLE_PATTERN,
        title="Unrecognized engine debug line",
        summary="Pattern hash 0xdeadbeef",
        occurrence_count_delta=2,
        new_evidence_ids=["evt_1", "evt_2"],
        corroboration_note="Seen twice in 5 seconds",
    )
    result = ReviewBatchResult(
        review_batch_id=batch_id,
        session_id=session_id,
        sequence_start=1,
        sequence_end=20,
        reviewed_evidence_ids=["evt_1", "evt_2"],
        operations=[op],
        review_status="COMPLETED",
    )

    # First application
    findings1 = journal.apply_batch_result(result)
    assert len(findings1) == 1
    f1 = findings1[0]
    assert f1.finding_id == finding_id
    assert f1.revision == 1
    assert f1.occurrence_count == 2
    assert f1.evidence_refs == ["evt_1", "evt_2"]
    assert batch_id in f1.applied_review_batch_ids

    # Second application of THE EXACT SAME BATCH RESULT
    findings2 = journal.apply_batch_result(result)
    assert len(findings2) == 1
    f2 = findings2[0]
    # No duplicate revision, no increment to count, no duplicate refs!
    assert f2.revision == 1
    assert f2.occurrence_count == 2
    assert f2.evidence_refs == ["evt_1", "evt_2"]


def test_finding_lifecycle_evolution_with_new_batch(tmp_path: Path) -> None:
    session_id = "obs_evolution"
    session_dir = tmp_path / session_id
    journal = ReviewJournalManager(session_dir=session_dir, session_id=session_id)

    finding_id = compute_finding_id(session_id, "objective", "churn:fetid_pool")

    # Batch 1: creates finding as WATCHING
    batch1_id = compute_review_batch_id(session_id, 1, 10, ["evt_1"])
    op1 = FindingOperation(
        op="CREATE",
        finding_id=finding_id,
        category="objective",
        semantic_issue_key="churn:fetid_pool",
        status=FindingStatus.WATCHING,
        title="Fetid Pool objective reevaluated",
        summary="Objective flapping",
        occurrence_count_delta=1,
        new_evidence_ids=["evt_1"],
    )
    res1 = ReviewBatchResult(
        review_batch_id=batch1_id,
        session_id=session_id,
        sequence_start=1,
        sequence_end=10,
        reviewed_evidence_ids=["evt_1"],
        operations=[op1],
        review_status="COMPLETED",
    )
    journal.apply_batch_result(res1)

    # Batch 2: corroborates finding with user marker
    batch2_id = compute_review_batch_id(session_id, 11, 20, ["evt_2", "mrk_1"])
    op2 = FindingOperation(
        op="UPDATE",
        finding_id=finding_id,
        category="objective",
        semantic_issue_key="churn:fetid_pool",
        status=FindingStatus.CORROBORATED,
        title="Fetid Pool objective reevaluated",
        summary="Objective flapping confirmed by player marker",
        occurrence_count_delta=1,
        new_evidence_ids=["evt_2", "mrk_1"],
        corroboration_note="Corroborated by user marker mrk_1",
    )
    res2 = ReviewBatchResult(
        review_batch_id=batch2_id,
        session_id=session_id,
        sequence_start=11,
        sequence_end=20,
        reviewed_evidence_ids=["evt_2", "mrk_1"],
        operations=[op2],
        review_status="COMPLETED",
    )
    findings = journal.apply_batch_result(res2)
    assert len(findings) == 1
    f = findings[0]
    assert f.finding_id == finding_id
    assert f.status == FindingStatus.CORROBORATED
    assert f.revision == 2
    assert f.occurrence_count == 2
    assert f.evidence_refs == ["evt_1", "evt_2", "mrk_1"]
    assert "Corroborated by user marker mrk_1" in f.corroboration_notes


def test_crash_case_b_and_c_recovery(tmp_path: Path) -> None:
    session_id = "obs_crash_recovery"
    session_dir = tmp_path / session_id
    journal = ReviewJournalManager(session_dir=session_dir, session_id=session_id)
    cursor_mgr = ReviewCursorManager(
        cursor_path=session_dir / "live_analysis" / "hermes_review_cursor.json",
        session_id=session_id,
    )

    batch_id = compute_review_batch_id(session_id, 1, 50, ["evt_10"])
    op = FindingOperation(
        op="CREATE",
        finding_id=compute_finding_id(session_id, "telemetry", "backpressure"),
        category="telemetry",
        semantic_issue_key="backpressure",
        status=FindingStatus.POSSIBLE_PATTERN,
        title="Observer queue backpressure",
        summary="Queue reached 950 items",
        occurrence_count_delta=1,
        new_evidence_ids=["evt_10"],
    )
    result = ReviewBatchResult(
        review_batch_id=batch_id,
        session_id=session_id,
        sequence_start=1,
        sequence_end=50,
        reviewed_evidence_ids=["evt_10"],
        operations=[op],
        review_status="COMPLETED",
    )

    # Case B: Batch result exists on disk, but process crashed before applying to findings/cursor
    journal.save_batch_result(result)
    assert cursor_mgr.review_contiguous_frontier == 0

    # Resume: journal can check if batch result already exists, apply findings and advance cursor
    recovered_res = journal.load_batch_result(batch_id)
    assert recovered_res is not None
    journal.apply_batch_result(recovered_res)
    cursor_mgr.record_batch_reviewed(batch_id, recovered_res.sequence_start, recovered_res.sequence_end)
    cursor_mgr.save_atomic()

    assert cursor_mgr.review_contiguous_frontier == 50
    f = journal.get_findings()[0]
    assert f.revision == 1

    # Case C: Crash right after findings applied, before cursor advanced (replayed again)
    journal.apply_batch_result(recovered_res)
    assert f.revision == 1
    assert f.occurrence_count == 1


def test_case_d_no_finding_batch(tmp_path: Path) -> None:
    session_id = "obs_no_finding"
    session_dir = tmp_path / session_id
    journal = ReviewJournalManager(session_dir=session_dir, session_id=session_id)
    cursor_mgr = ReviewCursorManager(
        cursor_path=session_dir / "live_analysis" / "hermes_review_cursor.json",
        session_id=session_id,
    )

    batch_id = compute_review_batch_id(session_id, 1, 100, ["evt_1", "evt_2"])
    result = ReviewBatchResult(
        review_batch_id=batch_id,
        session_id=session_id,
        sequence_start=1,
        sequence_end=100,
        reviewed_evidence_ids=["evt_1", "evt_2"],
        operations=[],
        review_status="COMPLETED",
    )

    journal.save_batch_result(result)
    journal.apply_batch_result(result)
    cursor_mgr.record_batch_reviewed(batch_id, 1, 100)
    cursor_mgr.save_atomic()

    # Cursor advances to 100
    assert cursor_mgr.review_contiguous_frontier == 100
    # Zero fake findings emitted
    assert len(journal.get_findings()) == 0
