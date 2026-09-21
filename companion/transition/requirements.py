"""Tri-state requirement evaluation and future requirement isolation engine.

Implements Milestone 3 Phase 3 (Tasks 3.1, 3.2):
- Tri-state RequirementReadiness (SATISFIED, UNSATISFIED, UNKNOWN).
- Structured RequirementEvaluation model.
- Strict future requirement isolation (e.g. Cast on Dodge [58, 100] at level 52).
- Source trust gating (PENDING_SOURCE_VERIFICATION / UNAVAILABLE cannot block or deadlock).
- Requirement aggregators consuming M2 BuildDeltaResult and M1 CharacterState.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, ConfigDict, Field

from companion.build.eligibility import EligibilityState, evaluate_eligibility
from companion.build.validation import validate_character_level
from companion.rules.evaluator import evaluate_rule
from companion.rules.loader import load_guide_rules
from companion.rules.schema import (
    GuideRule,
    RequirementType,
    RuleEvaluationState,
    SourceVerificationStatus,
    TransitionRuleRole,
)
from companion.sources.interval import IntervalKind, LevelInterval
from companion.sources.models_normalized import is_cast_on_dodge_id

if TYPE_CHECKING:
    from companion.build.delta import BuildDeltaResult
    from companion.state.schema import CharacterState


class RequirementReadiness(str, Enum):
    """Tri-state requirement readiness condition for progression transitions."""
    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    UNKNOWN = "UNKNOWN"


class RequirementEvaluation(BaseModel):
    """Structured evaluation of a guide rule within transition context."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    rule_id: str
    rule_name: str
    transition_role: TransitionRuleRole
    source_status: SourceVerificationStatus
    readiness: RequirementReadiness
    eligibility: EligibilityState | None = None
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_satisfied(self) -> bool:
        """True if the requirement is definitively satisfied."""
        return self.readiness == RequirementReadiness.SATISFIED

    @property
    def is_unsatisfied(self) -> bool:
        """True if the requirement is definitively unsatisfied."""
        return self.readiness == RequirementReadiness.UNSATISFIED

    @property
    def is_unknown(self) -> bool:
        """True if the requirement readiness is unknown or incomplete."""
        return self.readiness == RequirementReadiness.UNKNOWN

    @property
    def is_applicable_blocker(self) -> bool:
        """True if this evaluation represents a currently applicable USABLE blocking rule.

        Excludes FUTURE, EXPIRED, NOT_APPLICABLE, PENDING, UNAVAILABLE, and non-BLOCKING roles.
        """
        return (
            self.transition_role == TransitionRuleRole.BLOCKING_REQUIREMENT
            and self.source_status == SourceVerificationStatus.USABLE
            and self.eligibility not in (EligibilityState.FUTURE, EligibilityState.EXPIRED)
            and self.reason not in (
                "LEVEL_BELOW_MINIMUM",
                "LEVEL_ABOVE_MAXIMUM",
                "NOT_APPLICABLE",
                "INEVALUABLE_RULE",
                "PENDING_SOURCE_VERIFICATION",
                "UNAVAILABLE_RULE_SOURCE",
            )
        )

    @property
    def is_active_blocker(self) -> bool:
        """True if this requirement actively blocks transition (applicable USABLE and UNSATISFIED).

        UNKNOWN and SATISFIED requirements are strictly excluded from active blockers.
        """
        return self.is_applicable_blocker and self.readiness == RequirementReadiness.UNSATISFIED


def _extract_character_level(character_state: Any) -> int | None:
    """Extract and validate integer character level from CharacterState or dict."""
    if character_state is None:
        return None
    if hasattr(character_state, "level"):
        lvl_field = character_state.level
        if hasattr(lvl_field, "value"):
            return validate_character_level(lvl_field.value)
        return validate_character_level(lvl_field)
    if isinstance(character_state, dict) and "level" in character_state:
        lvl_val = character_state["level"]
        if isinstance(lvl_val, dict) and "value" in lvl_val:
            return validate_character_level(lvl_val["value"])
        return validate_character_level(lvl_val)
    return None


def evaluate_single_requirement(
    rule: GuideRule,
    evidence: Any = None,
    character_level: int | None = None,
    character_state: Any = None,
    details: dict[str, Any] | None = None,
) -> RequirementEvaluation:
    """Statelessly evaluate an individual GuideRule into a structured RequirementEvaluation.

    Enforces:
    - Tri-state mapping: SATISFIED, UNSATISFIED, UNKNOWN.
    - Stale, unobserved, partial, conflicting evidence -> UNKNOWN.
    - PENDING_SOURCE_VERIFICATION and UNAVAILABLE rules -> UNKNOWN with matching reason.
    - Level applicability boundaries: level < min_level -> FUTURE eligibility, UNKNOWN readiness.
    """
    merged_details: dict[str, Any] = {}
    if details:
        merged_details.update(details)

    # 1. Resolve character level
    valid_level = character_level
    if valid_level is None and character_state is not None:
        valid_level = _extract_character_level(character_state)
    else:
        valid_level = validate_character_level(valid_level)

    # 2. Resolve level eligibility
    elig_state: EligibilityState | None = None
    if rule.min_level is not None or rule.max_level is not None:
        min_l = rule.min_level if rule.min_level is not None else 1
        max_l = rule.max_level if rule.max_level is not None else 100
        interval = LevelInterval(kind=IntervalKind.RANGE, min_level=min_l, max_level=max_l)
        elig_eval = evaluate_eligibility(interval, valid_level)
        elig_state = elig_eval.state
    elif valid_level is not None:
        elig_state = EligibilityState.ACTIVE

    # Duck-typing check on evidence if from M2 delta
    if hasattr(evidence, "status"):
        ev_status = getattr(evidence.status, "value", str(evidence.status)).upper()
        if ev_status == "FUTURE":
            elig_state = EligibilityState.FUTURE
        elif ev_status == "EXPIRED":
            elig_state = EligibilityState.EXPIRED
        elif hasattr(evidence, "level_interval") and evidence.level_interval is not None:
            delta_elig = evaluate_eligibility(evidence.level_interval, valid_level).state
            if delta_elig == EligibilityState.FUTURE:
                elig_state = EligibilityState.FUTURE
            elif delta_elig == EligibilityState.EXPIRED and elig_state != EligibilityState.FUTURE:
                elig_state = EligibilityState.EXPIRED

    # 3. Evaluate rule condition via semantic rule evaluator
    rule_res = evaluate_rule(
        rule=rule,
        evidence=evidence,
        character_level=valid_level,
        character_state=character_state,
        details=merged_details,
    )

    merged_details.update(rule_res.details)
    merged_details["rule_evaluation_state"] = rule_res.state.value
    if valid_level is not None:
        merged_details["character_level"] = valid_level

    # 4. Determine Readiness and Reason
    readiness: RequirementReadiness
    reason: str | None = None

    if rule.source_status != SourceVerificationStatus.USABLE:
        readiness = RequirementReadiness.UNKNOWN
        reason = rule_res.reason or rule.source_status.value
    elif elig_state == EligibilityState.FUTURE or rule_res.reason == "LEVEL_BELOW_MINIMUM":
        readiness = RequirementReadiness.UNKNOWN
        reason = "LEVEL_BELOW_MINIMUM"
        elig_state = EligibilityState.FUTURE
    elif elig_state == EligibilityState.EXPIRED or rule_res.reason == "LEVEL_ABOVE_MAXIMUM":
        readiness = RequirementReadiness.UNKNOWN
        reason = "LEVEL_ABOVE_MAXIMUM"
        elig_state = EligibilityState.EXPIRED
    elif rule_res.state == RuleEvaluationState.PASS:
        readiness = RequirementReadiness.SATISFIED
        reason = None
    elif rule_res.state == RuleEvaluationState.FAIL:
        readiness = RequirementReadiness.UNSATISFIED
        reason = rule_res.reason or "CONDITION_UNSATISFIED"
    else:
        # STALE, CONFLICTING_EVIDENCE, UNKNOWN, NOT_APPLICABLE
        readiness = RequirementReadiness.UNKNOWN
        reason = rule_res.reason or rule_res.state.value

    return RequirementEvaluation(
        rule_id=rule.id,
        rule_name=rule.name or rule.id,
        transition_role=rule.transition_role,
        source_status=rule.source_status,
        readiness=readiness,
        eligibility=elig_state,
        reason=reason,
        details=merged_details,
    )


def _find_delta_evidence_for_rule(
    rule: GuideRule,
    delta: BuildDeltaResult,
) -> Any:
    """Find matching M2 BuildDeltaResult evidence for a given GuideRule."""
    # 1. Check for conflicts affecting this rule or entity
    for conflict in delta.conflicts:
        if (
            conflict.field_name == rule.id
            or (rule.expected and conflict.field_name == rule.expected.get("passive_id"))
            or (conflict.details and rule.id in conflict.details)
        ):
            return RuleEvaluationState.CONFLICTING_EVIDENCE

    # 2. Match by requirement type
    if rule.requirement_type in (RequirementType.SKILL, RequirementType.GEM):
        is_cod_rule = (
            rule.id == "GEM_CAST_ON_DODGE"
            or "cast_on_dodge" in rule.id.lower()
            or "cast on dodge" in (rule.name or "").lower()
        )
        for s in delta.skills:
            if is_cod_rule and (
                is_cast_on_dodge_id(s.primary_gem_id)
                or s.is_meta_gem
                or "castondodge" in s.primary_gem_id.lower()
                or (s.child_active_gem_id and "castondodge" in s.child_active_gem_id.lower())
            ):
                return s

            if rule.expected:
                expected_gem = (
                    rule.expected.get("gem_id")
                    or rule.expected.get("skill_id")
                    or rule.expected.get("primary_gem_id")
                )
                if expected_gem and (
                    s.primary_gem_id == expected_gem or s.logical_key[0] == expected_gem
                ):
                    return s

            if rule.id in (s.primary_gem_id, s.logical_key[0]):
                return s

    elif rule.requirement_type in (RequirementType.EQUIPMENT, RequirementType.ITEM):
        expected_slot = None
        expected_item = None
        if rule.expected:
            expected_slot = rule.expected.get("slot") or rule.expected.get("slot_id")
            expected_item = rule.expected.get("item_name")

        for eq in delta.equipment:
            if expected_slot and eq.slot_id.lower() == expected_slot.lower():
                return eq
            if expected_item and eq.item_name == expected_item:
                return eq
            if rule.id.lower() == eq.slot_id.lower():
                return eq

    elif rule.requirement_type == RequirementType.PASSIVE:
        expected_passive = rule.expected.get("passive_id") if rule.expected else None
        for p in delta.passives:
            if expected_passive and p.passive_id == expected_passive:
                return p
            if rule.id == p.passive_id or (rule.name and rule.name == p.name):
                return p

    return None


def evaluate_requirements(
    rules: list[GuideRule] | None = None,
    delta: BuildDeltaResult | None = None,
    character_state: CharacterState | None = None,
    character_level: int | None = None,
    evidence_map: dict[str, Any] | None = None,
) -> list[RequirementEvaluation]:
    """Evaluate a collection of guide rules against M2 delta and character state.

    Deterministic aggregator returning RequirementEvaluation for each rule.
    """
    resolved_rules = rules if rules is not None else load_guide_rules()

    # Determine character level
    resolved_level = character_level
    if resolved_level is None and character_state is not None:
        resolved_level = _extract_character_level(character_state)
    if resolved_level is None and delta is not None:
        resolved_level = validate_character_level(delta.character_level)

    evaluations: list[RequirementEvaluation] = []

    for rule in resolved_rules:
        # Match evidence
        matched_evidence: Any = None
        if evidence_map is not None and rule.id in evidence_map:
            matched_evidence = evidence_map[rule.id]
        elif delta is not None:
            matched_evidence = _find_delta_evidence_for_rule(rule, delta)

        eval_res = evaluate_single_requirement(
            rule=rule,
            evidence=matched_evidence,
            character_level=resolved_level,
            character_state=character_state,
        )
        evaluations.append(eval_res)

    return evaluations


def get_active_blocking_requirements(
    evaluations: list[RequirementEvaluation],
) -> list[RequirementEvaluation]:
    """Return applicable USABLE blocking requirements that are currently UNSATISFIED.

    Excludes:
    - Requirements with progression state FUTURE or EXPIRED
    - Rules that are NOT_APPLICABLE
    - Rules with source status PENDING_SOURCE_VERIFICATION or UNAVAILABLE
    - Rules with role ADVISORY, PREPARATION, or COMPLETION_EVIDENCE
    - Requirements with readiness UNKNOWN or SATISFIED
    """
    return [e for e in evaluations if e.is_active_blocker]


def get_applicable_blocking_requirements(
    evaluations: list[RequirementEvaluation],
) -> list[RequirementEvaluation]:
    """Return all currently applicable USABLE rules with role BLOCKING_REQUIREMENT."""
    return [e for e in evaluations if e.is_applicable_blocker]


def has_unsatisfied_blocker(evaluations: list[RequirementEvaluation]) -> bool:
    """Return True if any applicable USABLE blocking requirement is UNSATISFIED."""
    return any(e.is_active_blocker for e in evaluations)


def has_unknown_blocker(evaluations: list[RequirementEvaluation]) -> bool:
    """Return True if any applicable USABLE blocking requirement has UNKNOWN readiness."""
    return any(e.is_applicable_blocker and e.is_unknown for e in evaluations)


def is_transition_ready(evaluations: list[RequirementEvaluation]) -> bool:
    """Return True if all currently applicable USABLE blocking requirements are SATISFIED.

    Returns False if any applicable blocker is UNKNOWN or UNSATISFIED.
    PENDING_SOURCE_VERIFICATION, UNAVAILABLE, and FUTURE requirements are excluded
    and never block readiness.
    """
    blockers = get_applicable_blocking_requirements(evaluations)
    if not blockers:
        return True
    return all(e.is_satisfied for e in blockers)
