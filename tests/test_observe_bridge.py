"""Unit tests for Review Bridge request generation, coverage, and claim management."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import pytest

from companion.observe.bridge import (
    RequestCoverageManager,
    ReviewBridgeCoordinator,
    ReviewClaimManager,
    TestReviewResponder,
)
from companion.observe.models import (
    ExistingFindingContext,
    FindingOperationModel,
    ReviewClaimEnvelope,
    ReviewRequestEnvelope,
)


@pytest.fixture
def session_env(tmp_path: Path):
    sdir = tmp_path / "runtime" / "observations" / "sess_test_01"
    sdir.mkdir(parents=True, exist_ok=True)
    live_dir = sdir / "live_analysis"
    live_dir.mkdir(parents=True, exist_ok=True)
    return sdir, "sess_test_01"


def test_request_coverage_manager_non_overlapping_invariant():
    mgr = RequestCoverageManager()
    assert mgr.can_cover_range(1, 50)
    mgr.register_range(1, 50, "batch_1")

    # Overlaps are rejected
    assert not mgr.can_cover_range(25, 75)
    assert not mgr.can_cover_range(1, 50)
    assert not mgr.can_cover_range(50, 60)
    assert mgr.can_cover_range(51, 100)

    # Sequence query
    assert mgr.get_owning_batch(25) == "batch_1"
    assert mgr.get_owning_batch(51) is None


def test_request_coverage_reconstruction_from_disk(session_env):
    sdir, session_id = session_env
    live_dir = sdir / "live_analysis"
    req_dir = live_dir / "review_requests"
    req_dir.mkdir(parents=True, exist_ok=True)

    # Write two existing request files
    req1 = ReviewRequestEnvelope(
        review_batch_id="batch_1",
        session_id=session_id,
        sequence_start=1,
        sequence_end=50,
        evidence_ids=[f"evt_{i}" for i in range(1, 51)],
    )
    (req_dir / "batch_1.json").write_text(req1.model_dump_json(), encoding="utf-8")

    req2 = ReviewRequestEnvelope(
        review_batch_id="batch_2",
        session_id=session_id,
        sequence_start=51,
        sequence_end=100,
        evidence_ids=[f"evt_{i}" for i in range(51, 101)],
    )
    (req_dir / "batch_2.json").write_text(req2.model_dump_json(), encoding="utf-8")

    mgr = RequestCoverageManager()
    mgr.reconstruct_from_session(sdir)

    assert not mgr.can_cover_range(1, 50)
    assert not mgr.can_cover_range(51, 100)
    assert mgr.can_cover_range(101, 150)
    assert mgr.get_owning_batch(30) == "batch_1"
    assert mgr.get_owning_batch(75) == "batch_2"


def test_immutable_review_request_generation_and_write(session_env):
    sdir, session_id = session_env
    coordinator = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)

    req = coordinator.create_review_request(
        sequence_start=1,
        sequence_end=20,
        evidence_ids=["evt_1", "evt_2"],
        high_priority_signals=[],
    )

    req_file = sdir / "live_analysis" / "review_requests" / f"{req.review_batch_id}.json"
    assert req_file.exists()
    initial_content = req_file.read_text(encoding="utf-8")

    # Calling again for same range preserves existing request without overwrite
    req_dup = coordinator.create_review_request(
        sequence_start=1,
        sequence_end=20,
        evidence_ids=["evt_1", "evt_2"],
    )
    assert req_dup.review_batch_id == req.review_batch_id
    assert req_file.read_text(encoding="utf-8") == initial_content


def test_marker_inside_pending_batch_elevates_priority_without_overlap(session_env):
    sdir, session_id = session_env
    coordinator = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)

    req = coordinator.create_review_request(
        sequence_start=101,
        sequence_end=150,
        evidence_ids=[f"evt_{i}" for i in range(101, 151)],
    )

    assert coordinator.get_request_priority(req.review_batch_id) == "NORMAL"

    # Marker sequence 125 arrives inside existing batch
    promoted = coordinator.handle_marker_arrival(marker_sequence=125, marker_id="m1")
    assert promoted == req.review_batch_id
    assert coordinator.get_request_priority(req.review_batch_id) == "HIGH_MARKER"

    # Verify request JSON file remains bit-for-bit unchanged
    req_file = sdir / "live_analysis" / "review_requests" / f"{req.review_batch_id}.json"
    loaded = ReviewRequestEnvelope.model_validate_json(req_file.read_text(encoding="utf-8"))
    assert loaded.sequence_start == 101
    assert loaded.sequence_end == 150


def test_claim_management_distinct_claimants_and_safe_renewal(session_env):
    sdir, session_id = session_env
    claim_mgr = ReviewClaimManager(session_dir=sdir)

    batch_id = "batch_claim_test"

    # Claimant A claims batch
    claim_a = claim_mgr.claim_request(
        review_batch_id=batch_id,
        claim_id="clm_A",
        review_run_id="run_A",
        lease_seconds=180,
    )
    claim_file_a = sdir / "live_analysis" / "review_claims" / f"{batch_id}.clm_A.json"
    assert claim_file_a.exists()
    assert claim_mgr.is_claim_active(batch_id, "clm_A")

    # Claimant B claims same batch
    claim_b = claim_mgr.claim_request(
        review_batch_id=batch_id,
        claim_id="clm_B",
        review_run_id="run_B",
        lease_seconds=180,
    )
    claim_file_b = sdir / "live_analysis" / "review_claims" / f"{batch_id}.clm_B.json"
    assert claim_file_b.exists()

    # Both claim files coexist without overwriting
    assert claim_file_a.exists()
    assert claim_file_b.exists()

    # Self-owned lease renewal for Claimant A
    claim_mgr.renew_lease(batch_id, "clm_A", lease_seconds=300)
    status_file_a = sdir / "live_analysis" / "review_claim_status" / f"{batch_id}.clm_A.json"
    assert status_file_a.exists()
    assert not (sdir / "live_analysis" / "review_claim_status" / f"{batch_id}.clm_B.json").exists()


def test_stale_claim_lease_expiration_and_recovery(session_env):
    sdir, session_id = session_env
    claim_mgr = ReviewClaimManager(session_dir=sdir)

    batch_id = "batch_stale_test"
    expired_time = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()

    # Create an expired claim
    claim = ReviewClaimEnvelope(
        review_batch_id=batch_id,
        claim_id="clm_old",
        review_run_id="run_old",
        claimed_at=expired_time,
        lease_expires_at=expired_time,
    )
    claim_file = sdir / "live_analysis" / "review_claims" / f"{batch_id}.clm_old.json"
    claim_file.parent.mkdir(parents=True, exist_ok=True)
    claim_file.write_text(claim.model_dump_json(), encoding="utf-8")

    assert not claim_mgr.is_claim_active(batch_id, "clm_old")

    # Second reviewer can claim without erasing clm_old
    new_claim = claim_mgr.claim_request(
        review_batch_id=batch_id,
        claim_id="clm_new",
        review_run_id="run_new",
        lease_seconds=180,
    )
    assert claim_file.exists()  # Old provenance preserved
    assert claim_mgr.is_claim_active(batch_id, "clm_new")


def test_coordinator_and_test_responder_e2e_cycle(session_env):
    sdir, session_id = session_env
    coordinator = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)
    responder = TestReviewResponder(session_dir=sdir, run_id="run_test_bot")

    # 1. Emit request
    req = coordinator.create_review_request(
        sequence_start=1,
        sequence_end=10,
        evidence_ids=[f"evt_{i}" for i in range(1, 11)],
    )
    assert (sdir / "live_analysis" / "review_requests" / f"{req.review_batch_id}.json").exists()

    # 2. Responder discovers and claims
    discovered = responder.discover_pending_requests()
    assert len(discovered) == 1
    assert discovered[0].review_batch_id == req.review_batch_id

    claim = responder.claim(discovered[0], claim_id="clm_01")
    assert (sdir / "live_analysis" / "review_claims" / f"{req.review_batch_id}.clm_01.json").exists()

    # 3. Responder publishes candidate response
    op = FindingOperationModel(
        op="CREATE_FINDING",
        category="marker",
        semantic_issue_key="boss_glitch",
        classification="CORROBORATED",
        safe_summary="Boss attack delay glitch observed",
        evidence_refs=["evt_5"],
    )
    resp = responder.respond(request=discovered[0], claim=claim, operations=[op])
    assert (sdir / "live_analysis" / "review_responses" / f"{req.review_batch_id}.clm_01.json").exists()

    # 4. Coordinator polls and processes candidate response
    processed = coordinator.poll_and_process_responses()
    assert processed == 1

    # Canonical batch result persisted
    batch_file = sdir / "live_analysis" / "review_batches" / f"{req.review_batch_id}.json"
    assert batch_file.exists()

    # Findings journaled
    findings = coordinator.journal.get_findings()
    assert len(findings) == 1
    assert "boss_glitch" in findings[0].semantic_issue_key

    # Review cursor advanced to 10
    cursor = coordinator.cursor_mgr.load()
    assert cursor.review_contiguous_frontier == 10
    assert cursor.reviewed_ahead_ranges == []


def test_concurrency_arbitration_first_valid_wins(session_env):
    sdir, session_id = session_env
    coordinator = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)
    responder_a = TestReviewResponder(session_dir=sdir, run_id="run_A")
    responder_b = TestReviewResponder(session_dir=sdir, run_id="run_B")

    req = coordinator.create_review_request(
        sequence_start=1,
        sequence_end=5,
        evidence_ids=[f"evt_{i}" for i in range(1, 6)],
    )

    # Both claimants claim the same request
    claim_a = responder_a.claim(req, claim_id="clm_A")
    claim_b = responder_b.claim(req, claim_id="clm_B")

    # Claimant A authors response
    op_a = FindingOperationModel(
        op="CREATE_FINDING",
        category="anomaly",
        semantic_issue_key="issue_from_A",
        classification="CORROBORATED",
        safe_summary="Summary from A",
        evidence_refs=["evt_1"],
    )
    resp_a = responder_a.respond(req, claim_a, operations=[op_a])

    # Claimant B authors competing response
    op_b = FindingOperationModel(
        op="CREATE_FINDING",
        category="anomaly",
        semantic_issue_key="issue_from_B",
        classification="CORROBORATED",
        safe_summary="Summary from B",
        evidence_refs=["evt_2"],
    )
    resp_b = responder_b.respond(req, claim_b, operations=[op_b])

    # Process A first -> promoted
    ok_a, _ = coordinator.process_candidate_response(resp_a)
    assert ok_a is True

    canonical_result = coordinator.journal.load_batch_result(req.review_batch_id)
    assert canonical_result is not None
    assert canonical_result.operations[0].semantic_issue_key == "issue_from_A"

    # Process B second -> rejected without overwriting A's canonical result
    ok_b, err_b = coordinator.process_candidate_response(resp_b)
    assert ok_b is False
    assert "already has canonical result" in err_b

    unchanged_result = coordinator.journal.load_batch_result(req.review_batch_id)
    assert unchanged_result.operations[0].semantic_issue_key == "issue_from_A"


def test_out_of_order_review_and_contiguous_frontier_catchup(session_env):
    sdir, session_id = session_env
    coordinator = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)
    responder = TestReviewResponder(session_dir=sdir, run_id="run_test")

    # Batch 1 (1..10) and Batch 2 (11..20)
    req1 = coordinator.create_review_request(
        sequence_start=1,
        sequence_end=10,
        evidence_ids=[f"evt_{i}" for i in range(1, 11)],
    )
    req2 = coordinator.create_review_request(
        sequence_start=11,
        sequence_end=20,
        evidence_ids=[f"evt_{i}" for i in range(11, 21)],
        priority="HIGH_MARKER",
    )

    # Review Batch 2 FIRST (out of order priority review)
    claim2 = responder.claim(req2, claim_id="clm_02")
    resp2 = responder.respond(req2, claim2)
    ok2, _ = coordinator.process_candidate_response(resp2)
    assert ok2 is True

    # Review cursor frontier must hold at 0, while [11, 20] is in reviewed_ahead_ranges
    cursor_mid = coordinator.cursor_mgr.load()
    assert cursor_mid.review_contiguous_frontier == 0
    assert [11, 20] in cursor_mid.reviewed_ahead_ranges

    # Now Batch 1 completes
    claim1 = responder.claim(req1, claim_id="clm_01")
    resp1 = responder.respond(req1, claim1)
    ok1, _ = coordinator.process_candidate_response(resp1)
    assert ok1 is True

    # Review cursor frontier catches up contiguously to 20, and reviewed_ahead_ranges is absorbed
    cursor_final = coordinator.cursor_mgr.load()
    assert cursor_final.review_contiguous_frontier == 20
    assert cursor_final.reviewed_ahead_ranges == []

