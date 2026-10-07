"""Unit tests for the 8-point companion ingress validation gate in ReviewBridgeCoordinator."""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from companion.observe.bridge import validate_ingress_response
from companion.observe.models import (
    ExistingFindingContext,
    FindingOperationModel,
    ReviewClaimEnvelope,
    ReviewRequestEnvelope,
    ReviewResponseEnvelope,
)


@pytest.fixture
def valid_setup():
    session_id = "sess_val_01"
    batch_id = "batch_val_01"
    claim_id = "clm_val_01"
    run_id = "run_val_01"

    request = ReviewRequestEnvelope(
        review_batch_id=batch_id,
        session_id=session_id,
        sequence_start=101,
        sequence_end=110,
        evidence_ids=[f"evt_{i}" for i in range(101, 111)],
    )

    claim = ReviewClaimEnvelope(
        review_batch_id=batch_id,
        claim_id=claim_id,
        review_run_id=run_id,
        claimed_at=datetime.now(timezone.utc).isoformat(),
        lease_expires_at=(datetime.now(timezone.utc)).isoformat(),
    )

    active_finding_ids = {"find:sess_val_01:marker:stuck_terrain"}

    response = ReviewResponseEnvelope(
        review_batch_id=batch_id,
        session_id=session_id,
        sequence_start=101,
        sequence_end=110,
        accounted_evidence_ids=[f"evt_{i}" for i in range(101, 111)],
        claim_id=claim_id,
        review_run_id=run_id,
        operations=[
            FindingOperationModel(
                op="UPDATE_FINDING",
                target_finding_id="find:sess_val_01:marker:stuck_terrain",
                category="marker",
                classification="CORROBORATED",
                safe_summary="Corroborated stuck terrain marker",
                evidence_refs=["evt_101", "evt_102"],
            )
        ],
    )

    return session_id, request, claim, active_finding_ids, response


def test_ingress_valid_response_passes(valid_setup):
    session_id, request, claim, active_finding_ids, response = valid_setup
    valid, err = validate_ingress_response(
        response=response,
        session_id=session_id,
        request=request,
        claim=claim,
        active_finding_ids=active_finding_ids,
    )
    assert valid is True
    assert err is None


def test_ingress_rule_1_provenance_mismatch(valid_setup):
    session_id, request, claim, active_finding_ids, response = valid_setup
    # Wrong claim ID
    bad_resp = response.model_copy(update={"claim_id": "clm_other"})
    valid, err = validate_ingress_response(
        response=bad_resp,
        session_id=session_id,
        request=request,
        claim=claim,
        active_finding_ids=active_finding_ids,
    )
    assert valid is False
    assert "claim_id mismatch" in err


def test_ingress_rule_3_and_4_session_and_bounds_mismatch(valid_setup):
    session_id, request, claim, active_finding_ids, response = valid_setup
    bad_session = response.model_copy(update={"session_id": "wrong_session"})
    valid, err = validate_ingress_response(
        response=bad_session,
        session_id=session_id,
        request=request,
        claim=claim,
        active_finding_ids=active_finding_ids,
    )
    assert valid is False
    assert "session_id mismatch" in err

    bad_seq = response.model_copy(update={"sequence_start": 999})
    valid, err = validate_ingress_response(
        response=bad_seq,
        session_id=session_id,
        request=request,
        claim=claim,
        active_finding_ids=active_finding_ids,
    )
    assert valid is False
    assert "sequence bounds mismatch" in err


def test_ingress_rule_5_evidence_accounting(valid_setup):
    session_id, request, claim, active_finding_ids, response = valid_setup

    # Partial accounting (only 2 out of 10 accounted)
    partial_resp = response.model_copy(update={"accounted_evidence_ids": ["evt_101", "evt_102"]})
    valid, err = validate_ingress_response(
        response=partial_resp,
        session_id=session_id,
        request=request,
        claim=claim,
        active_finding_ids=active_finding_ids,
    )
    assert valid is False
    assert "evidence accounting mismatch" in err

    # Duplicate accounted evidence ID
    dup_ids = [f"evt_{i}" for i in range(101, 111)]
    dup_ids[1] = dup_ids[0]
    dup_resp = response.model_copy(update={"accounted_evidence_ids": dup_ids})
    valid, err = validate_ingress_response(
        response=dup_resp,
        session_id=session_id,
        request=request,
        claim=claim,
        active_finding_ids=active_finding_ids,
    )
    assert valid is False
    assert "duplicate accounted evidence" in err

    # Unknown evidence ID
    unk_ids = [f"evt_{i}" for i in range(101, 110)] + ["evt_alien"]
    unk_resp = response.model_copy(update={"accounted_evidence_ids": unk_ids})
    valid, err = validate_ingress_response(
        response=unk_resp,
        session_id=session_id,
        request=request,
        claim=claim,
        active_finding_ids=active_finding_ids,
    )
    assert valid is False
    assert "unknown evidence" in err


def test_ingress_rule_6_finding_identity_integrity(valid_setup):
    session_id, request, claim, active_finding_ids, response = valid_setup

    # UPDATE_FINDING with nonexistent ID
    bad_op = FindingOperationModel(
        op="UPDATE_FINDING",
        target_finding_id="find:sess_val_01:marker:nonexistent",
        category="marker",
        classification="CORROBORATED",
        safe_summary="Nonexistent update",
        evidence_refs=["evt_101"],
    )
    bad_resp = response.model_copy(update={"operations": [bad_op]})
    valid, err = validate_ingress_response(
        response=bad_resp,
        session_id=session_id,
        request=request,
        claim=claim,
        active_finding_ids=active_finding_ids,
    )
    assert valid is False
    assert "target_finding_id does not exist" in err

    # Path traversal in target_finding_id
    traversal_op = FindingOperationModel(
        op="UPDATE_FINDING",
        target_finding_id="../../evil_path",
        category="marker",
        classification="CORROBORATED",
        safe_summary="Traversal update",
        evidence_refs=["evt_101"],
    )
    bad_resp = response.model_copy(update={"operations": [traversal_op]})
    valid, err = validate_ingress_response(
        response=bad_resp,
        session_id=session_id,
        request=request,
        claim=claim,
        active_finding_ids=active_finding_ids,
    )
    assert valid is False
    assert "invalid target_finding_id characters" in err


def test_ingress_rule_8_targeted_privacy_and_security(valid_setup):
    session_id, request, claim, active_finding_ids, response = valid_setup

    # PoE chat prefix in safe_summary
    chat_op = FindingOperationModel(
        op="CREATE_FINDING",
        category="chat",
        semantic_issue_key="leak",
        classification="WATCHING",
        safe_summary="@From player: hello world trade",
        evidence_refs=["evt_101"],
    )
    chat_resp = response.model_copy(update={"operations": [chat_op]})
    valid, err = validate_ingress_response(
        response=chat_resp,
        session_id=session_id,
        request=request,
        claim=claim,
        active_finding_ids=active_finding_ids,
    )
    assert valid is False
    assert "PoE chat / whisper pattern" in err

    # Credential token leak
    cred_op = FindingOperationModel(
        op="CREATE_FINDING",
        category="leak",
        semantic_issue_key="token",
        classification="WATCHING",
        safe_summary="Found secret Bearer eyJhbGciOi...",
        evidence_refs=["evt_101"],
    )
    cred_resp = response.model_copy(update={"operations": [cred_op]})
    valid, err = validate_ingress_response(
        response=cred_resp,
        session_id=session_id,
        request=request,
        claim=claim,
        active_finding_ids=active_finding_ids,
    )
    assert valid is False
    assert "credential / secret pattern" in err

    # Valid punctuation and percent signs are NOT rejected
    clean_tech_op = FindingOperationModel(
        op="CREATE_FINDING",
        category="quality",
        semantic_issue_key="flameblast_quality",
        classification="WATCHING",
        safe_summary="Flameblast quality remained below 40% (expected >=50% in maps)!",
        evidence_refs=["evt_101"],
    )
    clean_resp = response.model_copy(update={"operations": [clean_tech_op]})
    valid, err = validate_ingress_response(
        response=clean_resp,
        session_id=session_id,
        request=request,
        claim=claim,
        active_finding_ids=active_finding_ids,
    )
    assert valid is True
    assert err is None
