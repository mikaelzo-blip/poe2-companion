"""Semantic rule evaluator and source trust gating engine.

Pure, deterministic, stateless evaluation of declarative guide rules against
evidence, character state, and applicability boundaries.
Strictly preserves the 6 semantic states: PASS, FAIL, UNKNOWN, NOT_APPLICABLE,
STALE, and CONFLICTING_EVIDENCE.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from companion.rules.schema import (
    GuideRule,
    RuleEvaluationState,
    SourceVerificationStatus,
    TransitionRuleRole,
)
from companion.state.provenance import VerificationState


class RuleEvaluationResult(BaseModel):
    """Semantic evaluation outcome for an individual declarative guide rule."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    rule_id: str
    state: RuleEvaluationState
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    transition_role: TransitionRuleRole
    source_status: SourceVerificationStatus


class RuleEvidence(BaseModel):
    """Structured evidence container for rule condition evaluation."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    satisfied: bool | None = None
    is_stale: bool = False
    is_conflicting: bool = False
    is_observed: bool = True
    raw_evidence: Any = None
    details: dict[str, Any] = Field(default_factory=dict)


def _resolve_candidate_evidence(
    evidence: Any,
) -> tuple[RuleEvaluationState, str | None, dict[str, Any]]:
    """Map raw evidence into a preliminary semantic state, reason, and details."""
    if evidence is None:
        return RuleEvaluationState.UNKNOWN, "NO_EVIDENCE", {}

    # Strict bool check (isinstance(True, int) is True, so check bool first)
    if isinstance(evidence, bool):
        if evidence:
            return RuleEvaluationState.PASS, None, {"raw_evidence": True}
        return RuleEvaluationState.FAIL, "CONDITION_UNSATISFIED", {"raw_evidence": False}

    if isinstance(evidence, RuleEvaluationState):
        reason: str | None = None
        if evidence == RuleEvaluationState.STALE:
            reason = "STALE_EVIDENCE"
        elif evidence == RuleEvaluationState.CONFLICTING_EVIDENCE:
            reason = "CONFLICTING_EVIDENCE"
        elif evidence == RuleEvaluationState.UNKNOWN:
            reason = "UNKNOWN_EVIDENCE"
        elif evidence == RuleEvaluationState.NOT_APPLICABLE:
            reason = "NOT_APPLICABLE"
        return evidence, reason, {"raw_evidence": evidence.value}

    if isinstance(evidence, RuleEvidence):
        merged_details = dict(evidence.details)
        if evidence.raw_evidence is not None:
            merged_details["raw_evidence"] = evidence.raw_evidence
        if evidence.is_conflicting:
            return RuleEvaluationState.CONFLICTING_EVIDENCE, "CONFLICTING_EVIDENCE", merged_details
        if evidence.is_stale:
            return RuleEvaluationState.STALE, "STALE_EVIDENCE", merged_details
        if not evidence.is_observed:
            return RuleEvaluationState.UNKNOWN, "UNOBSERVED_EVIDENCE", merged_details
        if evidence.satisfied is True:
            return RuleEvaluationState.PASS, None, merged_details
        if evidence.satisfied is False:
            return RuleEvaluationState.FAIL, "CONDITION_UNSATISFIED", merged_details
        return RuleEvaluationState.UNKNOWN, "UNKNOWN_EVIDENCE", merged_details

    if isinstance(evidence, VerificationState):
        if evidence == VerificationState.STALE:
            return RuleEvaluationState.STALE, "STALE_EVIDENCE", {"verification_state": evidence.value}
        if evidence == VerificationState.CONFLICTING:
            return (
                RuleEvaluationState.CONFLICTING_EVIDENCE,
                "CONFLICTING_EVIDENCE",
                {"verification_state": evidence.value},
            )
        if evidence == VerificationState.UNKNOWN:
            return RuleEvaluationState.UNKNOWN, "UNKNOWN_EVIDENCE", {"verification_state": evidence.value}
        return RuleEvaluationState.PASS, None, {"verification_state": evidence.value}

    if isinstance(evidence, str):
        ev_upper = evidence.strip().upper()
        if ev_upper in ("PASS", "SATISFIED", "MET", "PRESENT", "TRUE"):
            return RuleEvaluationState.PASS, None, {"raw_evidence": evidence}
        if ev_upper in ("FAIL", "UNSATISFIED", "FAILED", "MISSING", "FALSE"):
            return RuleEvaluationState.FAIL, "CONDITION_UNSATISFIED", {"raw_evidence": evidence}
        if ev_upper in ("STALE", "STALE_EVIDENCE", "STALE_PLAYER_STATE"):
            return RuleEvaluationState.STALE, "STALE_EVIDENCE", {"raw_evidence": evidence}
        if ev_upper in ("CONFLICTING", "CONFLICTING_EVIDENCE", "CONFLICT"):
            return (
                RuleEvaluationState.CONFLICTING_EVIDENCE,
                "CONFLICTING_EVIDENCE",
                {"raw_evidence": evidence},
            )
        if ev_upper in ("UNKNOWN", "UNOBSERVED", "NO_EVIDENCE"):
            return RuleEvaluationState.UNKNOWN, "UNOBSERVED_EVIDENCE", {"raw_evidence": evidence}
        if ev_upper in ("NOT_APPLICABLE", "NA", "N/A"):
            return RuleEvaluationState.NOT_APPLICABLE, "NOT_APPLICABLE", {"raw_evidence": evidence}
        return (
            RuleEvaluationState.UNKNOWN,
            f"UNRECOGNIZED_EVIDENCE_STRING:{evidence}",
            {"raw_evidence": evidence},
        )

    if isinstance(evidence, dict):
        merged = dict(evidence)
        if evidence.get("is_conflicting") or evidence.get("conflicting"):
            return RuleEvaluationState.CONFLICTING_EVIDENCE, "CONFLICTING_EVIDENCE", merged
        if evidence.get("is_stale"):
            return RuleEvaluationState.STALE, "STALE_EVIDENCE", merged
        if evidence.get("is_observed") is False or evidence.get("observed") is False:
            return RuleEvaluationState.UNKNOWN, "UNOBSERVED_EVIDENCE", merged
        if "state" in evidence:
            raw_st = evidence["state"]
            if isinstance(raw_st, RuleEvaluationState):
                return raw_st, None, merged
            if isinstance(raw_st, str):
                return _resolve_candidate_evidence(raw_st)[0], None, merged
        if "satisfied" in evidence:
            sat = evidence["satisfied"]
            if sat is True:
                return RuleEvaluationState.PASS, None, merged
            if sat is False:
                return RuleEvaluationState.FAIL, "CONDITION_UNSATISFIED", merged
            return RuleEvaluationState.UNKNOWN, "UNKNOWN_EVIDENCE", merged
        if "status" in evidence:
            return _resolve_candidate_evidence(evidence["status"])
        return RuleEvaluationState.UNKNOWN, "UNKNOWN_EVIDENCE", merged

    # Support M2 DeltaEntry duck typing
    if hasattr(evidence, "status"):
        st_val = getattr(evidence.status, "value", str(evidence.status))
        st_upper = str(st_val).upper()
        details = {"delta_status": st_upper}
        if hasattr(evidence, "reason"):
            details["delta_reason"] = getattr(evidence.reason, "value", str(evidence.reason))

        if st_upper == "PRESENT":
            return RuleEvaluationState.PASS, None, details
        if st_upper == "MISSING":
            return RuleEvaluationState.FAIL, "CONDITION_UNSATISFIED", details
        if st_upper == "UNKNOWN":
            reason_attr = str(getattr(evidence, "reason", ""))
            if "STALE" in reason_attr.upper():
                return RuleEvaluationState.STALE, "STALE_EVIDENCE", details
            return RuleEvaluationState.UNKNOWN, "UNKNOWN_EVIDENCE", details
        if st_upper in ("FUTURE", "EXPIRED"):
            return RuleEvaluationState.NOT_APPLICABLE, "NOT_APPLICABLE", details

    return RuleEvaluationState.UNKNOWN, "UNKNOWN_EVIDENCE_TYPE", {"raw_evidence": str(evidence)}


def evaluate_rule(
    rule: GuideRule,
    evidence: Any = None,
    character_level: int | None = None,
    character_state: Any = None,
    details: dict[str, Any] | None = None,
) -> RuleEvaluationResult:
    """Evaluate a single GuideRule against evidence and character context.

    Stateless, deterministic evaluator mapping evaluations into 6 explicit states:
    `PASS`, `FAIL`, `UNKNOWN`, `NOT_APPLICABLE`, `STALE`, `CONFLICTING_EVIDENCE`.

    Key invariants:
    - `UNKNOWN != FAIL`, `STALE != FAIL`, `CONFLICTING_EVIDENCE != FAIL`.
    - Unobserved evidence produces `UNKNOWN` (reason `NO_EVIDENCE`).
    - Stale evidence produces `STALE` (reason `STALE_EVIDENCE`).
    - Contradictory evidence produces `CONFLICTING_EVIDENCE`.
    - Outside level applicability produces `NOT_APPLICABLE`.
    - Inevaluable rule produces `UNKNOWN` (reason `INEVALUABLE_RULE`).
    - Rules with `PENDING_SOURCE_VERIFICATION` or `UNAVAILABLE` are clamped to `UNKNOWN`
      with reasons `PENDING_SOURCE_VERIFICATION` and `UNAVAILABLE_RULE_SOURCE` respectively,
      preventing unverified external rules from asserting PASS or FAIL.
    """
    merged_details: dict[str, Any] = {}
    if details:
        merged_details.update(details)

    # 1. Resolve character level from character_state if not explicitly provided
    resolved_level = character_level
    if resolved_level is None and character_state is not None:
        if hasattr(character_state, "level"):
            lvl_field = character_state.level
            if hasattr(lvl_field, "value"):
                resolved_level = lvl_field.value
            elif isinstance(lvl_field, int):
                resolved_level = lvl_field
        elif isinstance(character_state, dict) and "level" in character_state:
            lvl_val = character_state["level"]
            if isinstance(lvl_val, dict) and "value" in lvl_val:
                resolved_level = lvl_val["value"]
            elif isinstance(lvl_val, int):
                resolved_level = lvl_val

    # 2. Check level applicability boundaries
    if resolved_level is not None:
        if rule.min_level is not None and resolved_level < rule.min_level:
            merged_details.update({"character_level": resolved_level, "min_level": rule.min_level})
            return RuleEvaluationResult(
                rule_id=rule.id,
                state=RuleEvaluationState.NOT_APPLICABLE,
                reason="LEVEL_BELOW_MINIMUM",
                details=merged_details,
                transition_role=rule.transition_role,
                source_status=rule.source_status,
            )
        if rule.max_level is not None and resolved_level > rule.max_level:
            merged_details.update({"character_level": resolved_level, "max_level": rule.max_level})
            return RuleEvaluationResult(
                rule_id=rule.id,
                state=RuleEvaluationState.NOT_APPLICABLE,
                reason="LEVEL_ABOVE_MAXIMUM",
                details=merged_details,
                transition_role=rule.transition_role,
                source_status=rule.source_status,
            )

    # 3. Check evaluability
    if not rule.evaluable:
        merged_details.update({"evaluable": False})
        return RuleEvaluationResult(
            rule_id=rule.id,
            state=RuleEvaluationState.UNKNOWN,
            reason="INEVALUABLE_RULE",
            details=merged_details,
            transition_role=rule.transition_role,
            source_status=rule.source_status,
        )

    # 4. Resolve candidate evidence state
    candidate_state, candidate_reason, ev_details = _resolve_candidate_evidence(evidence)
    merged_details.update(ev_details)

    # 5. Enforce Source Verification Trust Gating
    if rule.source_status == SourceVerificationStatus.UNAVAILABLE:
        merged_details.update({
            "raw_state": candidate_state.value,
            "blocked_by_source_status": SourceVerificationStatus.UNAVAILABLE.value,
        })
        return RuleEvaluationResult(
            rule_id=rule.id,
            state=RuleEvaluationState.UNKNOWN,
            reason="UNAVAILABLE_RULE_SOURCE",
            details=merged_details,
            transition_role=rule.transition_role,
            source_status=rule.source_status,
        )

    if rule.source_status == SourceVerificationStatus.PENDING_SOURCE_VERIFICATION:
        merged_details.update({
            "raw_state": candidate_state.value,
            "blocked_by_source_status": SourceVerificationStatus.PENDING_SOURCE_VERIFICATION.value,
        })
        return RuleEvaluationResult(
            rule_id=rule.id,
            state=RuleEvaluationState.UNKNOWN,
            reason="PENDING_SOURCE_VERIFICATION",
            details=merged_details,
            transition_role=rule.transition_role,
            source_status=rule.source_status,
        )

    return RuleEvaluationResult(
        rule_id=rule.id,
        state=candidate_state,
        reason=candidate_reason,
        details=merged_details,
        transition_role=rule.transition_role,
        source_status=rule.source_status,
    )
