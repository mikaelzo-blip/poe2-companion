"""Comprehensive deterministic verification suite for the Filesystem Hermes AI Review Bridge.

Validates:
- ACCOUNTING (exact match, partial/duplicate/unknown detection)
- FINDING IDENTITY (CREATE, corroborating UPDATE, invalid target rejection, distinct F2)
- CLAIMS & LEASES (multi-claim concurrency, first-writer canonical promotion, no overwrite, stale takeover)
- REQUEST COVERAGE & PRIORITY METADATA (non-overlapping ranges, marker escalation without duplication)
- FRONTIER & OUT-OF-ORDER REVIEW (contiguous progression, reviewed_ahead_ranges, catch-up)
- PRIVACY & WRITE ALLOWLIST SAFETY
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import pytest

from companion.observe.bridge import (
    RequestCoverageManager,
    ReviewBridgeCoordinator,
    ReviewClaimManager,
    TestReviewResponder,
    validate_ingress_response,
)
from companion.observe.cursor import ReviewCursorManager
from companion.observe.journal import ReviewJournalManager
from companion.observe.models import (
    ExistingFindingContext,
    FindingOperationModel,
    ReviewClaimEnvelope,
    ReviewRequestEnvelope,
    ReviewResponseEnvelope,
)


@pytest.fixture
def env(tmp_path: Path):
    sdir = tmp_path / "runtime" / "observations" / "sess_suite_01"
    sdir.mkdir(parents=True, exist_ok=True)
    live_dir = sdir / "live_analysis"
    live_dir.mkdir(parents=True, exist_ok=True)
    return sdir, "sess_suite_01"


# ---------------------------------------------------------------------------
# 1. ACCOUNTING
# ---------------------------------------------------------------------------


def test_suite_accounting(env):
    sdir, session_id = env
    req = ReviewRequestEnvelope(
        review_batch_id="batch_acc",
        session_id=session_id,
        sequence_start=1,
        sequence_end=10,
        evidence_ids=[f"ev_{i}" for i in range(1, 11)],
    )
    claim = ReviewClaimEnvelope(
        review_batch_id="batch_acc",
        claim_id="clm_acc",
        review_run_id="run_acc",
        claimed_at=datetime.now(timezone.utc).isoformat(),
        lease_expires_at=(datetime.now(timezone.utc) + timedelta(seconds=180)).isoformat(),
    )
    (sdir / "live_analysis" / "review_claims" / f"{req.review_batch_id}.clm_acc.json").parent.mkdir(
        parents=True, exist_ok=True
    )
    (sdir / "live_analysis" / "review_claims" / f"{req.review_batch_id}.clm_acc.json").write_text(
        claim.model_dump_json(), encoding="utf-8"
    )

    # 1. Partial accounted rejected (only 2 out of 10 accounted)
    resp_partial = ReviewResponseEnvelope(
        schema_version="1.0",
        review_batch_id="batch_acc",
        session_id=session_id,
        sequence_start=1,
        sequence_end=10,
        claim_id="clm_acc",
        review_run_id="run_acc",
        accounted_evidence_ids=["ev_1", "ev_2"],
        operations=[
            FindingOperationModel(
                op="CREATE_FINDING",
                category="RUNTIME_ANOMALY",
                semantic_issue_key="key_1",
                classification="LIKELY_DEFECT",
                safe_summary="Valid summary",
                evidence_refs=["ev_1", "ev_2"],
            )
        ],
    )
    ok, err = validate_ingress_response(resp_partial, session_id, req, claim, set())
    assert not ok
    assert "missing 8 of 10" in err

    # 2. Complete accounting accepted (all 10 accounted, finding references 2)
    resp_complete = ReviewResponseEnvelope(
        schema_version="1.0",
        review_batch_id="batch_acc",
        session_id=session_id,
        sequence_start=1,
        sequence_end=10,
        claim_id="clm_acc",
        review_run_id="run_acc",
        accounted_evidence_ids=[f"ev_{i}" for i in range(1, 11)],
        operations=[
            FindingOperationModel(
                op="CREATE_FINDING",
                category="RUNTIME_ANOMALY",
                semantic_issue_key="key_1",
                classification="LIKELY_DEFECT",
                safe_summary="Valid summary",
                evidence_refs=["ev_1", "ev_2"],
            )
        ],
    )
    ok, err = validate_ingress_response(resp_complete, session_id, req, claim, set())
    assert ok
    assert err is None

    # 3. NO_FINDING with all accounted accepted
    resp_no_finding = ReviewResponseEnvelope(
        schema_version="1.0",
        review_batch_id="batch_acc",
        session_id=session_id,
        sequence_start=1,
        sequence_end=10,
        claim_id="clm_acc",
        review_run_id="run_acc",
        accounted_evidence_ids=[f"ev_{i}" for i in range(1, 11)],
        operations=[],
    )
    ok, err = validate_ingress_response(resp_no_finding, session_id, req, claim, set())
    assert ok
    assert err is None

    # 4. Duplicate accounted ID rejected
    resp_dup = ReviewResponseEnvelope(
        schema_version="1.0",
        review_batch_id="batch_acc",
        session_id=session_id,
        sequence_start=1,
        sequence_end=10,
        claim_id="clm_acc",
        review_run_id="run_acc",
        accounted_evidence_ids=["ev_1", "ev_1"] + [f"ev_{i}" for i in range(2, 11)],
        operations=[],
    )
    ok, err = validate_ingress_response(resp_dup, session_id, req, claim, set())
    assert not ok
    assert "duplicate accounted evidence IDs" in err

    # 5. Unknown evidence ID rejected
    resp_unknown = ReviewResponseEnvelope(
        schema_version="1.0",
        review_batch_id="batch_acc",
        session_id=session_id,
        sequence_start=1,
        sequence_end=10,
        claim_id="clm_acc",
        review_run_id="run_acc",
        accounted_evidence_ids=[f"ev_{i}" for i in range(1, 11)] + ["ev_alien"],
        operations=[],
    )
    ok, err = validate_ingress_response(resp_unknown, session_id, req, claim, set())
    assert not ok
    assert "unknown evidence ids" in err.lower()


# ---------------------------------------------------------------------------
# 2. FINDING IDENTITY
# ---------------------------------------------------------------------------


def test_suite_finding_identity(env):
    sdir, session_id = env
    coord = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)
    responder = TestReviewResponder(session_dir=sdir, run_id="run_fid")

    # 1. Batch 1: CREATE_FINDING creates F1
    req1 = coord.create_review_request(
        sequence_start=1,
        sequence_end=20,
        evidence_ids=[f"e_{i}" for i in range(1, 21)],
    )
    claim1 = responder.claim(req1)
    op1 = FindingOperationModel(
        op="CREATE_FINDING",
        category="RUNTIME_ANOMALY",
        semantic_issue_key="perf_drop_cpu",
        classification="LIKELY_DEFECT",
        safe_summary="CPU spike observed at 60fps drop",
        evidence_refs=["e_1", "e_2"],
    )
    resp1 = responder.respond(req1, claim1, operations=[op1])
    ok, err = coord.process_candidate_response(resp1)
    assert ok is True, f"Error: {err}"

    journal_mgr = ReviewJournalManager(session_dir=sdir, session_id=session_id)
    findings = journal_mgr.get_findings()
    assert len(findings) == 1
    f1 = findings[0]
    assert f1.semantic_issue_key == "perf_drop_cpu"
    f1_id = f1.finding_id

    # 2. Batch 2: existing_findings is populated with F1
    req2 = coord.create_review_request(
        sequence_start=21,
        sequence_end=40,
        evidence_ids=[f"e_{i}" for i in range(21, 41)],
    )
    assert len(req2.existing_findings) == 1
    assert req2.existing_findings[0].finding_id == f1_id

    # 3. Later batch UPDATE_FINDING with target_finding_id = F1 updates without spawning duplicate
    claim2 = responder.claim(req2)
    op2_update = FindingOperationModel(
        op="UPDATE_FINDING",
        target_finding_id=f1_id,
        category="RUNTIME_ANOMALY",
        semantic_issue_key="perf_drop_cpu",
        classification="CORROBORATED",
        safe_summary="Corroborated CPU spike continues with additional frames",
        evidence_refs=["e_21", "e_22"],
    )
    resp2 = responder.respond(req2, claim2, operations=[op2_update])
    ok, err = coord.process_candidate_response(resp2)
    assert ok is True

    findings2 = journal_mgr.get_findings()
    assert len(findings2) == 1  # No duplicate F2 spawned!
    assert findings2[0].finding_id == f1_id
    assert "Corroborated" in findings2[0].summary

    # 4. Invalid/nonexistent target_finding_id rejected by 8-point gate
    req3 = coord.create_review_request(
        sequence_start=41,
        sequence_end=60,
        evidence_ids=[f"e_{i}" for i in range(41, 61)],
    )
    claim3 = responder.claim(req3)
    op3_invalid = FindingOperationModel(
        op="UPDATE_FINDING",
        target_finding_id="f_nonexistent_999",
        category="RUNTIME_ANOMALY",
        semantic_issue_key="perf_drop_cpu",
        classification="LIKELY_DEFECT",
        safe_summary="Updating ghost finding",
        evidence_refs=["e_41"],
    )
    resp3_bad = responder.respond(req3, claim3, operations=[op3_invalid])
    ok, err = coord.process_candidate_response(resp3_bad)
    assert not ok
    assert "does not exist in active session findings: f_nonexistent_999" in err

    # 5. Unrelated issue creates distinct finding F2
    op3_distinct = FindingOperationModel(
        op="CREATE_FINDING",
        category="SYSTEM_HEALTH",
        semantic_issue_key="disk_io_thrashing",
        classification="WATCHING",
        safe_summary="Disk write latency exceeded 500ms",
        evidence_refs=["e_41", "e_42"],
    )
    resp3_good = responder.respond(req3, claim3, operations=[op3_distinct])
    ok, err = coord.process_candidate_response(resp3_good)
    assert ok is True

    findings3 = journal_mgr.get_findings()
    assert len(findings3) == 2
    f_keys = {f.semantic_issue_key for f in findings3}
    assert f_keys == {"perf_drop_cpu", "disk_io_thrashing"}


# ---------------------------------------------------------------------------
# 3. CLAIMS & LEASES
# ---------------------------------------------------------------------------


def test_suite_claims_and_leases(env):
    sdir, session_id = env
    coord = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)
    claim_mgr = ReviewClaimManager(session_dir=sdir)

    req = coord.create_review_request(
        sequence_start=1,
        sequence_end=20,
        evidence_ids=[f"evt_{i}" for i in range(1, 21)],
    )
    b_id = req.review_batch_id
    req_file = sdir / "live_analysis" / "review_requests" / f"{b_id}.json"
    req_content_initial = req_file.read_text(encoding="utf-8")

    # 1. Two Hermes tasks create different claim IDs without overwriting
    resp_a = TestReviewResponder(session_dir=sdir, run_id="run_agent_A")
    resp_b = TestReviewResponder(session_dir=sdir, run_id="run_agent_B")

    claim_a = resp_a.claim(req, claim_id="clm_A")
    claim_b = resp_b.claim(req, claim_id="clm_B")

    file_a = sdir / "live_analysis" / "review_claims" / f"{b_id}.clm_A.json"
    file_b = sdir / "live_analysis" / "review_claims" / f"{b_id}.clm_B.json"

    # 2. Both claim artifacts remain durably inspectable simultaneously on disk
    assert file_a.exists()
    assert file_b.exists()
    assert json.loads(file_a.read_text(encoding="utf-8"))["claim_id"] == "clm_A"
    assert json.loads(file_b.read_text(encoding="utf-8"))["claim_id"] == "clm_B"

    # 3. Candidate response files (<batch_id>.<claim_id>.json) cannot overwrite one another
    candidate_a = resp_a.respond(req, claim_a, operations=[])
    candidate_b = resp_b.respond(req, claim_b, operations=[])

    cand_file_a = sdir / "live_analysis" / "review_responses" / f"{b_id}.clm_A.json"
    cand_file_b = sdir / "live_analysis" / "review_responses" / f"{b_id}.clm_B.json"
    assert cand_file_a.exists()
    assert cand_file_b.exists()

    # 4. Response A validates against claim A and response B validates against claim B
    ok_a, _ = validate_ingress_response(candidate_a, session_id, req, claim_a, set())
    ok_b, _ = validate_ingress_response(candidate_b, session_id, req, claim_b, set())
    assert ok_a and ok_b

    # 5. First valid response promoted to canonical ReviewBatchResult
    ok, err = coord.process_candidate_response(candidate_a)
    assert ok is True
    canonical_file = sdir / "live_analysis" / "review_batches" / f"{b_id}.json"
    assert canonical_file.exists()
    canonical_data = json.loads(canonical_file.read_text(encoding="utf-8"))
    assert canonical_data["claim_id"] == "clm_A"

    # 6. Later valid response from Agent B cannot replace canonical ReviewBatchResult
    ok2, err2 = coord.process_candidate_response(candidate_b)
    assert not ok2
    assert "already has canonical result" in err2
    # Verify canonical file was NOT touched
    canonical_data_after = json.loads(canonical_file.read_text(encoding="utf-8"))
    assert canonical_data_after["claim_id"] == "clm_A"

    # 7. Immutable request file never rewritten
    assert req_file.read_text(encoding="utf-8") == req_content_initial

    # 8. Slow reviewer (> 60s) safe under conservative 180s lease
    active_now = claim_mgr.is_claim_active(b_id, "clm_A")
    assert active_now is True

    # 9. Stale claim (> 180s) allows takeover without erasing old provenance
    past_iso = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()
    old_claim_provenance = ReviewClaimEnvelope(
        review_batch_id="b_stale",
        claim_id="clm_old",
        review_run_id="run_old",
        claimed_at=past_iso,
        lease_expires_at=past_iso,
    )
    stale_claim_file = sdir / "live_analysis" / "review_claims" / "b_stale.clm_old.json"
    stale_claim_file.write_text(old_claim_provenance.model_dump_json(), encoding="utf-8")

    assert not claim_mgr.is_claim_active("b_stale", "clm_old")
    # File still exists on disk (provenance preserved)
    assert stale_claim_file.exists()


# ---------------------------------------------------------------------------
# 4. REQUEST COVERAGE & PRIORITY METADATA
# ---------------------------------------------------------------------------


def test_suite_request_coverage_and_priority_metadata(env):
    sdir, session_id = env
    coord = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)

    # 1. Canonical request ranges never overlap across batches (101-150, 151-200, 201-250)
    req1 = coord.create_review_request(
        sequence_start=101,
        sequence_end=150,
        evidence_ids=[f"ev_{i}" for i in range(101, 151)],
    )
    req2 = coord.create_review_request(
        sequence_start=151,
        sequence_end=200,
        evidence_ids=[f"ev_{i}" for i in range(151, 201)],
    )
    assert req1.sequence_start == 101 and req1.sequence_end == 150
    assert req2.sequence_start == 151 and req2.sequence_end == 200

    # 2. Same sequence cannot belong to two review requests
    with pytest.raises(ValueError, match="overlaps with existing request coverage"):
        coord.create_review_request(
            sequence_start=120,
            sequence_end=170,
            evidence_ids=["ev_120"],
        )

    # 3. Marker inside existing pending batch elevates scheduling priority instead of creating overlapping batch
    # Initial priority is NORMAL
    assert coord.get_request_priority(req1.review_batch_id) == "NORMAL"
    elevated = coord.elevate_priority(req1.review_batch_id, "HIGH_MARKER", "User dropped marker at seq 125")
    assert elevated is True
    assert coord.get_request_priority(req1.review_batch_id) == "HIGH_MARKER"

    # Priority file was created
    prio_file = sdir / "live_analysis" / "review_priority" / f"{req1.review_batch_id}.priority.json"
    assert prio_file.exists()
    pdata = json.loads(prio_file.read_text(encoding="utf-8"))
    assert pdata["priority"] == "HIGH_MARKER"

    # Immutable request file is UNTOUCHED
    req_file = sdir / "live_analysis" / "review_requests" / f"{req1.review_batch_id}.json"
    req_disk = ReviewRequestEnvelope.model_validate_json(req_file.read_text(encoding="utf-8"))
    assert req_disk.review_batch_id == req1.review_batch_id  # Batch ID did NOT change
    assert req_disk.sequence_start == 101 and req_disk.sequence_end == 150

    # 4. Marker outside existing coverage creates next canonical non-overlapping batch
    req3 = coord.create_review_request(
        sequence_start=201,
        sequence_end=250,
        evidence_ids=[f"ev_{i}" for i in range(201, 251)],
        priority="HIGH_MARKER",
        priority_reason="User marker at seq 220",
    )
    assert req3.sequence_start == 201 and req3.sequence_end == 250
    assert coord.get_request_priority(req3.review_batch_id) == "HIGH_MARKER"

    # 5. Restart reconstructs request coverage correctly from disk before generating new requests
    del coord
    coord_resumed = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)
    assert not coord_resumed.coverage_mgr.can_cover_range(110, 140)
    assert not coord_resumed.coverage_mgr.can_cover_range(160, 180)
    assert not coord_resumed.coverage_mgr.can_cover_range(210, 240)
    assert coord_resumed.coverage_mgr.can_cover_range(251, 300)


# ---------------------------------------------------------------------------
# 5. FRONTIER & OUT-OF-ORDER REVIEW
# ---------------------------------------------------------------------------


def test_suite_frontier_and_out_of_order_review(env):
    sdir, session_id = env

    # Set up initial frontier at 100
    cursor_mgr = ReviewCursorManager(
        cursor_path=sdir / "live_analysis" / "hermes_review_cursor.json",
        session_id=session_id,
    )
    cursor_mgr.record_batch_reviewed("batch_0", 1, 100)
    cursor_mgr.save_atomic()

    coord = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)
    responder = TestReviewResponder(session_dir=sdir, run_id="run_ooo")

    # Request A: routine batch 101-150
    req_a = coord.create_review_request(
        sequence_start=101,
        sequence_end=150,
        evidence_ids=[f"e_{i}" for i in range(101, 151)],
    )

    # Request B: priority marker batch 151-175
    req_b = coord.create_review_request(
        sequence_start=151,
        sequence_end=175,
        evidence_ids=[f"e_{i}" for i in range(151, 176)],
        priority="HIGH_MARKER",
    )

    # 1. Later marker batch (req_b) completed FIRST
    claim_b = responder.claim(req_b)
    resp_b = responder.respond(req_b, claim_b, operations=[])
    ok_b, err_b = coord.process_candidate_response(resp_b)
    assert ok_b is True

    # 2. Frontier does NOT jump past missing batch 101-150: stays at 100!
    c_state1 = cursor_mgr.load()
    assert c_state1.review_contiguous_frontier == 100
    assert c_state1.accounted_reviewed_ranges == [[151, 175]]

    # 3. Process restart preserves reviewed_ahead_ranges
    del coord
    coord_restarted = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)
    c_state_restarted = coord_restarted.cursor_mgr.load()
    assert c_state_restarted.review_contiguous_frontier == 100
    assert c_state_restarted.accounted_reviewed_ranges == [[151, 175]]

    # 4. Completed out-of-order batch is NOT re-generated as review request
    assert not coord_restarted.coverage_mgr.can_cover_range(151, 175)

    # 5. Frontier catches up contiguously after older batch completes!
    claim_a = responder.claim(req_a)
    resp_a = responder.respond(req_a, claim_a, operations=[])
    ok_a, err_a = coord_restarted.process_candidate_response(resp_a)
    assert ok_a is True

    c_state_final = coord_restarted.cursor_mgr.load()
    # Now both 101-150 and 151-175 are completed: frontier advances directly to 175!
    assert c_state_final.review_contiguous_frontier == 175
    assert c_state_final.accounted_reviewed_ranges == []


# ---------------------------------------------------------------------------
# 6. PRIVACY & SAFETY WRITE ALLOWLIST
# ---------------------------------------------------------------------------


def test_suite_privacy_and_safety_allowlist(env):
    sdir, session_id = env
    req = ReviewRequestEnvelope(
        review_batch_id="batch_sec",
        session_id=session_id,
        sequence_start=1,
        sequence_end=5,
        evidence_ids=[f"ev_{i}" for i in range(1, 6)],
    )
    claim = ReviewClaimEnvelope(
        review_batch_id="batch_sec",
        claim_id="clm_sec",
        review_run_id="run_sec",
        claimed_at=datetime.now(timezone.utc).isoformat(),
        lease_expires_at=(datetime.now(timezone.utc) + timedelta(seconds=180)).isoformat(),
    )
    (sdir / "live_analysis" / "review_claims" / f"{req.review_batch_id}.clm_sec.json").parent.mkdir(
        parents=True, exist_ok=True
    )
    (sdir / "live_analysis" / "review_claims" / f"{req.review_batch_id}.clm_sec.json").write_text(
        claim.model_dump_json(), encoding="utf-8"
    )

    # 1. Technical phrase "40% quality" accepted
    resp_tech = ReviewResponseEnvelope(
        schema_version="1.0",
        review_batch_id="batch_sec",
        session_id=session_id,
        sequence_start=1,
        sequence_end=5,
        claim_id="clm_sec",
        review_run_id="run_sec",
        accounted_evidence_ids=[f"ev_{i}" for i in range(1, 6)],
        operations=[
            FindingOperationModel(
                op="CREATE_FINDING",
                category="BUILD_PROGRESSION",
                semantic_issue_key="gem_quality_drop",
                classification="WATCHING",
                safe_summary="Item crafted with 40% quality flask catalyst",
                evidence_refs=["ev_1"],
            )
        ],
    )
    ok, err = validate_ingress_response(resp_tech, session_id, req, claim, set())
    assert ok
    assert err is None

    # 2. Real PoE whisper/chat sample rejected
    resp_whisper = ReviewResponseEnvelope(
        schema_version="1.0",
        review_batch_id="batch_sec",
        session_id=session_id,
        sequence_start=1,
        sequence_end=5,
        claim_id="clm_sec",
        review_run_id="run_sec",
        accounted_evidence_ids=[f"ev_{i}" for i in range(1, 6)],
        operations=[
            FindingOperationModel(
                op="CREATE_FINDING",
                category="BUILD_PROGRESSION",
                semantic_issue_key="chat_leak",
                classification="WATCHING",
                safe_summary="@From PlayerName: hi, want to buy your divine orb for 150 chaos",
                evidence_refs=["ev_1"],
            )
        ],
    )
    ok, err = validate_ingress_response(resp_whisper, session_id, req, claim, set())
    assert not ok
    assert "PoE chat / whisper pattern detected" in err

    # 3. Token/credential pattern rejected
    resp_token = ReviewResponseEnvelope(
        schema_version="1.0",
        review_batch_id="batch_sec",
        session_id=session_id,
        sequence_start=1,
        sequence_end=5,
        claim_id="clm_sec",
        review_run_id="run_sec",
        accounted_evidence_ids=[f"ev_{i}" for i in range(1, 6)],
        operations=[
            FindingOperationModel(
                op="CREATE_FINDING",
                category="SYSTEM_HEALTH",
                semantic_issue_key="cred_leak",
                classification="WATCHING",
                safe_summary="Failed request with token sk-proj-1234567890abcdef123456",
                evidence_refs=["ev_1"],
            )
        ],
    )
    ok, err = validate_ingress_response(resp_token, session_id, req, claim, set())
    assert not ok
    assert "credential / secret pattern detected" in err
