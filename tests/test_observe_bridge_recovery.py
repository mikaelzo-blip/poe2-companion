"""Tests for ReviewBridgeCoordinator interruption resilience, recovery, and resume ergonomics."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from companion.observe.bridge import (
    ReviewBridgeCoordinator,
    ReviewClaimManager,
    TestReviewResponder,
)
from companion.observe.models import (
    FindingOperationModel,
    ReviewClaimEnvelope,
    ReviewRequestEnvelope,
)


@pytest.fixture
def session_env(tmp_path: Path):
    sdir = tmp_path / "runtime" / "observations" / "sess_rec_01"
    sdir.mkdir(parents=True, exist_ok=True)
    live_dir = sdir / "live_analysis"
    live_dir.mkdir(parents=True, exist_ok=True)
    return sdir, "sess_rec_01"


def test_provider_interruption_preserves_immutable_requests(session_env):
    sdir, session_id = session_env
    coord1 = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)

    # 1. Coordinator creates request
    req = coord1.create_review_request(
        sequence_start=1,
        sequence_end=20,
        evidence_ids=[f"evt_{i}" for i in range(1, 21)],
    )
    req_file = sdir / "live_analysis" / "review_requests" / f"{req.review_batch_id}.json"
    assert req_file.exists()

    # 2. Simulate sudden interruption/crash of coordinator and reviewer
    del coord1

    # 3. Resume with new coordinator instance
    coord2 = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)
    assert not coord2.coverage_mgr.can_cover_range(1, 20)  # Reconstructed from disk
    assert coord2.coverage_mgr.get_owning_batch(10) == req.review_batch_id

    # Responder can discover and fulfill the request after resume
    responder = TestReviewResponder(session_dir=sdir, run_id="run_resumed")
    pending = responder.discover_pending_requests()
    assert len(pending) == 1
    assert pending[0].review_batch_id == req.review_batch_id

    claim = responder.claim(pending[0])
    resp = responder.respond(pending[0], claim)
    ok, _ = coord2.process_candidate_response(resp)
    assert ok is True
    assert coord2.cursor_mgr.load().review_contiguous_frontier == 20


def test_stale_claim_recovery_on_resume(session_env):
    sdir, session_id = session_env
    coord = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)
    claim_mgr = ReviewClaimManager(session_dir=sdir)

    req = coord.create_review_request(
        sequence_start=1,
        sequence_end=10,
        evidence_ids=[f"evt_{i}" for i in range(1, 11)],
    )

    # Old reviewer claimed and crashed 300 seconds ago (expired lease)
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
    old_claim = ReviewClaimEnvelope(
        review_batch_id=req.review_batch_id,
        claim_id="clm_dead",
        review_run_id="run_dead",
        claimed_at=old_time,
        lease_expires_at=old_time,
    )
    (sdir / "live_analysis" / "review_claims" / f"{req.review_batch_id}.clm_dead.json").write_text(
        old_claim.model_dump_json(), encoding="utf-8"
    )

    assert not claim_mgr.is_claim_active(req.review_batch_id, "clm_dead")

    # New reviewer resumes and acquires fresh claim
    responder = TestReviewResponder(session_dir=sdir, run_id="run_alive")
    new_claim = responder.claim(req, claim_id="clm_alive")
    assert claim_mgr.is_claim_active(req.review_batch_id, "clm_alive")

    resp = responder.respond(req, new_claim)
    ok, err = coord.process_candidate_response(resp)
    assert ok is True
    assert err is None


def test_marker_prioritization_across_resume(session_env):
    sdir, session_id = session_env
    coord1 = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)

    # Routine request A
    req_a = coord1.create_review_request(
        sequence_start=1,
        sequence_end=50,
        evidence_ids=[f"evt_{i}" for i in range(1, 51)],
        priority="NORMAL",
    )

    # Marker request B
    req_b = coord1.create_review_request(
        sequence_start=51,
        sequence_end=75,
        evidence_ids=[f"evt_{i}" for i in range(51, 76)],
        priority="HIGH_MARKER",
        priority_reason="Player marker",
    )

    # Simulate exit and resume
    del coord1
    coord2 = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)

    assert coord2.get_request_priority(req_a.review_batch_id) == "NORMAL"
    assert coord2.get_request_priority(req_b.review_batch_id) == "HIGH_MARKER"

    # Pending requests prioritized by priority metadata
    responder = TestReviewResponder(session_dir=sdir)
    pending = responder.discover_pending_requests()

    # Sort pending by coordinator priority
    pending.sort(
        key=lambda r: (
            0 if coord2.get_request_priority(r.review_batch_id) == "HIGH_MARKER" else 1,
            r.sequence_start,
        )
    )
    assert pending[0].review_batch_id == req_b.review_batch_id
    assert pending[1].review_batch_id == req_a.review_batch_id
