"""End-to-end simulation tests for the Filesystem Hermes AI Review Bridge.

Validates the full cycle:
1. Local reader frontier advances.
2. Immutable non-overlapping review request emitted.
3. Test responder claims and authors candidate response.
4. Bridge validates through 8-point ingress gate.
5. Canonical ReviewBatchResult persisted.
6. Findings journaled in hermes_findings.jsonl.
7. Review cursor advances contiguously.
8. Second cycle corroborates finding and reaches zero review lag.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest

from companion.observe.bridge import (
    ReviewBridgeCoordinator,
    TestReviewResponder,
)
from companion.observe.cursor import ReviewCursorManager, compute_review_lag
from companion.observe.journal import ReviewJournalManager
from companion.observe.manifest import ManifestManager, SessionManifest
from companion.observe.models import (
    EvidencePriority,
    FactKind,
    FindingOperationModel,
    HealthState,
    ManifestStatus,
    ObservationEnvelope,
)
from companion.observe.reader import IncrementalStreamReader


@pytest.fixture
def e2e_session(tmp_path: Path):
    sdir = tmp_path / "runtime" / "observations" / "sess_e2e_full"
    sdir.mkdir(parents=True, exist_ok=True)
    live_dir = sdir / "live_analysis"
    live_dir.mkdir(parents=True, exist_ok=True)

    manifest = SessionManifest(
        session_id="sess_e2e_full",
        runtime_run_id="run_e2e_01",
        started_at=datetime.now(timezone.utc).isoformat(),
        status=ManifestStatus.OPEN,
        sequence_high_watermark=100,
        persisted_event_count=100,
        health_state=HealthState.HEALTHY,
    )
    ManifestManager(sdir / "session_manifest.json").save_atomic(manifest)

    # Populate 100 observation events
    events_path = sdir / "events.jsonl"
    with open(events_path, "w", encoding="utf-8") as f:
        for seq in range(1, 101):
            env = ObservationEnvelope(
                observation_session_id="sess_e2e_full",
                sequence_number=seq,
                taxonomy=FactKind.OBSERVED_FACT,
                event_type="FRAME_METRIC",
                priority=EvidencePriority.LOW if seq != 25 else EvidencePriority.HIGH,
                payload={"seq": seq, "fps": 30 if seq == 25 else 60},
            )
            f.write(env.model_dump_json() + "\n")

    return sdir, "sess_e2e_full"


def test_complete_review_bridge_lifecycle_e2e(e2e_session):
    sdir, session_id = e2e_session

    # Step 1: Incremental stream reader advances frontier
    reader = IncrementalStreamReader(session_dir=sdir, session_id=session_id)
    envelopes = reader.read_new_envelopes()
    assert len(envelopes) == 100
    reader.save_state()
    assert reader.contiguous_frontier == 100

    # Step 2: Coordinator emits first immutable non-overlapping request (1..50)
    coord = ReviewBridgeCoordinator(session_dir=sdir, session_id=session_id)
    req1 = coord.create_review_request(
        sequence_start=1,
        sequence_end=50,
        evidence_ids=[f"ev_{i}" for i in range(1, 51)],
    )
    req1_file = sdir / "live_analysis" / "review_requests" / f"{req1.review_batch_id}.json"
    assert req1_file.exists()

    # Step 3: Test responder claims and authors candidate response with CREATE_FINDING
    responder = TestReviewResponder(session_dir=sdir, run_id="run_hermes_ai")
    pending = responder.discover_pending_requests()
    assert len(pending) == 1
    assert pending[0].review_batch_id == req1.review_batch_id

    claim1 = responder.claim(pending[0], claim_id="clm_batch1")
    op1 = FindingOperationModel(
        op="CREATE_FINDING",
        category="PERFORMANCE",
        semantic_issue_key="frame_drop_seq25",
        classification="LIKELY_DEFECT",
        safe_summary="Severe frame drop down to 30fps at seq 25",
        evidence_refs=["ev_25"],
    )
    resp1 = responder.respond(pending[0], claim1, operations=[op1])

    # Step 4: Coordinator validates 8-point gate and processes response
    ok1, err1 = coord.process_candidate_response(resp1)
    assert ok1 is True, f"Batch 1 processing failed: {err1}"

    # Step 5: Canonical batch result persisted in review_batches/
    batch1_file = sdir / "live_analysis" / "review_batches" / f"{req1.review_batch_id}.json"
    assert batch1_file.exists()
    b1_data = json.loads(batch1_file.read_text(encoding="utf-8"))
    assert b1_data["claim_id"] == "clm_batch1"
    assert b1_data["review_status"] == "COMPLETED"

    # Step 6: Findings journaled in hermes_findings.jsonl
    journal_mgr = ReviewJournalManager(session_dir=sdir, session_id=session_id)
    findings1 = journal_mgr.get_findings()
    assert len(findings1) == 1
    f1 = findings1[0]
    assert f1.semantic_issue_key == "frame_drop_seq25"
    assert f1.occurrence_count == 1
    f1_id = f1.finding_id

    # Step 7: Review cursor advanced contiguously
    cursor1 = coord.cursor_mgr.load()
    assert cursor1.review_contiguous_frontier == 50
    lag1 = compute_review_lag(reader.contiguous_frontier, cursor1.review_contiguous_frontier)
    assert lag1 == 50  # 100 - 50 = 50

    # Step 8: Second cycle: Next non-overlapping batch (51..100)
    req2 = coord.create_review_request(
        sequence_start=51,
        sequence_end=100,
        evidence_ids=[f"ev_{i}" for i in range(51, 101)],
    )
    # req2 contains existing_findings context pointing to f1_id
    assert len(req2.existing_findings) == 1
    assert req2.existing_findings[0].finding_id == f1_id

    claim2 = responder.claim(req2, claim_id="clm_batch2")
    op2 = FindingOperationModel(
        op="UPDATE_FINDING",
        target_finding_id=f1_id,
        category="PERFORMANCE",
        semantic_issue_key="frame_drop_seq25",
        classification="CORROBORATED",
        safe_summary="Frame stability recovered in sequence 51-100",
        evidence_refs=["ev_75"],
        corroboration_note="Corroborated recovery post-anomaly",
    )
    resp2 = responder.respond(req2, claim2, operations=[op2])

    ok2, err2 = coord.process_candidate_response(resp2)
    assert ok2 is True, f"Batch 2 processing failed: {err2}"

    # Step 9: Final verification: Finding updated, cursor at 100, lag is 0
    findings2 = journal_mgr.get_findings()
    assert len(findings2) == 1
    assert findings2[0].finding_id == f1_id
    assert findings2[0].occurrence_count == 2
    assert "Corroborated recovery" in findings2[0].corroboration_notes[0]

    cursor2 = coord.cursor_mgr.load()
    assert cursor2.review_contiguous_frontier == 100
    lag2 = compute_review_lag(reader.contiguous_frontier, cursor2.review_contiguous_frontier)
    assert lag2 == 0  # Reached zero review lag!
