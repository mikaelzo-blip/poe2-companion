"""Unit tests for Hermes review bridge models in companion.observe.models."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from companion.observe.models import (
    ExistingFindingContext,
    FindingOperationModel,
    RequestPriorityState,
    ReviewClaimEnvelope,
    ReviewClaimStatusEnvelope,
    ReviewRequestEnvelope,
    ReviewResponseEnvelope,
)


def test_existing_finding_context_serialization():
    ctx = ExistingFindingContext(
        finding_id="find:s1:parser:anomaly_x",
        category="parser",
        classification="LIKELY_DEFECT",
        safe_summary="Parser gap on unhandled line",
        relevant_subject_or_key="anomaly_x",
        evidence_count=3,
        recent_evidence_refs=["evt_1", "evt_2"],
    )
    raw = ctx.model_dump_json()
    loaded = ExistingFindingContext.model_validate_json(raw)
    assert loaded.finding_id == "find:s1:parser:anomaly_x"
    assert loaded.evidence_count == 3
    assert loaded.recent_evidence_refs == ["evt_1", "evt_2"]

    # Immutability
    with pytest.raises((ValidationError, TypeError)):
        loaded.evidence_count = 5


def test_review_request_envelope_immutability_and_defaults():
    req = ReviewRequestEnvelope(
        review_batch_id="batch_123",
        session_id="session_abc",
        sequence_start=101,
        sequence_end=150,
        evidence_ids=["evt_1", "evt_2"],
    )
    assert req.schema_version == "1.0"
    assert req.sequence_start == 101
    assert req.sequence_end == 150
    assert req.evidence_ids == ["evt_1", "evt_2"]
    assert "Do NOT reproduce private player chat" in req.privacy_instructions
    assert req.created_at is not None

    raw = req.model_dump_json()
    loaded = ReviewRequestEnvelope.model_validate_json(raw)
    assert loaded.review_batch_id == "batch_123"

    with pytest.raises((ValidationError, TypeError)):
        loaded.sequence_start = 200


def test_review_claim_and_status_envelopes():
    claimed_at = datetime.now(timezone.utc).isoformat()
    lease_expires = datetime.now(timezone.utc).isoformat()
    claim = ReviewClaimEnvelope(
        review_batch_id="batch_123",
        claim_id="clm_01",
        review_run_id="run_hermes_01",
        claimed_at=claimed_at,
        lease_expires_at=lease_expires,
    )
    assert claim.schema_version == "1.0"
    assert claim.claim_id == "clm_01"

    status = ReviewClaimStatusEnvelope(
        review_batch_id="batch_123",
        claim_id="clm_01",
        last_heartbeat=claimed_at,
        lease_expires_at=lease_expires,
    )
    assert status.claim_id == "clm_01"
    raw_status = status.model_dump_json()
    assert "clm_01" in raw_status


def test_request_priority_state():
    prio = RequestPriorityState(
        review_batch_id="batch_123",
        priority="HIGH_MARKER",
        priority_reason="User manual marker at seq 120",
    )
    assert prio.priority == "HIGH_MARKER"
    assert prio.priority_reason == "User manual marker at seq 120"
    assert prio.updated_at is not None


def test_finding_operation_model_and_review_response():
    op_create = FindingOperationModel(
        op="CREATE_FINDING",
        category="marker",
        semantic_issue_key="player_stuck",
        classification="CORROBORATED",
        safe_summary="Player stuck in terrain marker",
        evidence_refs=["evt_1"],
    )
    op_update = FindingOperationModel(
        op="UPDATE_FINDING",
        target_finding_id="find:s1:marker:player_stuck",
        category="marker",
        classification="LIKELY_DEFECT",
        safe_summary="Updated player stuck finding",
        evidence_refs=["evt_2"],
    )
    op_no_finding = FindingOperationModel(
        op="NO_FINDING",
        category="routine",
        safe_summary="Clean trace",
        evidence_refs=[],
    )

    resp = ReviewResponseEnvelope(
        review_batch_id="batch_123",
        session_id="session_abc",
        sequence_start=101,
        sequence_end=150,
        accounted_evidence_ids=["evt_1", "evt_2"],
        claim_id="clm_01",
        review_run_id="run_hermes_01",
        operations=[op_create, op_update, op_no_finding],
    )
    assert resp.claim_id == "clm_01"
    assert len(resp.operations) == 3
    assert resp.accounted_evidence_ids == ["evt_1", "evt_2"]

    raw = resp.model_dump_json()
    loaded = ReviewResponseEnvelope.model_validate_json(raw)
    assert len(loaded.operations) == 3
    assert loaded.operations[1].target_finding_id == "find:s1:marker:player_stuck"
