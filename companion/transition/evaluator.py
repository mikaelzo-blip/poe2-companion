"""Deterministic transition evaluator and trigger for Level-52 progression milestone.

Implements Milestone 3 Phase 4 (Task 4.2):
- evaluate_level52_transition: deterministic multi-state transition evaluation.
- trigger_transition_start: explicit trigger for READY -> TRANSITIONING.
- can_transition: topology validation for state transitions.
- Enforces strict future requirement isolation, uncertainty safety (VERIFYING never BLOCKED),
  source verification gating (pending rules do not deadlock READY), and late install resolution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from companion.build.eligibility import EligibilityState
from companion.build.validation import InvalidCharacterLevelError, validate_character_level
from companion.rules.loader import load_guide_rules
from companion.rules.schema import (
    GuideRule,
    SourceVerificationStatus,
    TransitionRuleRole,
)
from companion.transition.requirements import (
    RequirementEvaluation,
    RequirementReadiness,
    _extract_character_level,
    evaluate_requirements,
    get_applicable_blocking_requirements,
    has_unsatisfied_blocker,
)
from companion.transition.state import (
    Level52TransitionRecord,
    Level52TransitionResult,
    Level52TransitionState,
)

if TYPE_CHECKING:
    from companion.build.delta import BuildDeltaResult
    from companion.state.schema import CharacterState


class InvalidTransitionError(ValueError):
    """Raised when an invalid state transition is attempted."""
    pass


# Canonical allowed transitions matrix
_VALID_TRANSITIONS: dict[Level52TransitionState, set[Level52TransitionState]] = {
    Level52TransitionState.NOT_RELEVANT: {
        Level52TransitionState.NOT_RELEVANT,
        Level52TransitionState.PREPARING,
        Level52TransitionState.VERIFYING,
        Level52TransitionState.BLOCKED,
        Level52TransitionState.READY,
        Level52TransitionState.COMPLETE,
    },
    Level52TransitionState.PREPARING: {
        Level52TransitionState.PREPARING,
        Level52TransitionState.NOT_RELEVANT,
        Level52TransitionState.VERIFYING,
        Level52TransitionState.BLOCKED,
        Level52TransitionState.READY,
        Level52TransitionState.COMPLETE,
    },
    Level52TransitionState.VERIFYING: {
        Level52TransitionState.VERIFYING,
        Level52TransitionState.BLOCKED,
        Level52TransitionState.READY,
        Level52TransitionState.COMPLETE,
    },
    Level52TransitionState.BLOCKED: {
        Level52TransitionState.BLOCKED,
        Level52TransitionState.VERIFYING,
        Level52TransitionState.READY,
        Level52TransitionState.COMPLETE,
    },
    Level52TransitionState.READY: {
        Level52TransitionState.READY,
        Level52TransitionState.VERIFYING,
        Level52TransitionState.BLOCKED,
        Level52TransitionState.TRANSITIONING,
        Level52TransitionState.COMPLETE,
    },
    Level52TransitionState.TRANSITIONING: {
        Level52TransitionState.TRANSITIONING,
        Level52TransitionState.VERIFYING,
        Level52TransitionState.BLOCKED,
        Level52TransitionState.COMPLETE,
    },
    Level52TransitionState.COMPLETE: {
        Level52TransitionState.COMPLETE,
    },
}


def can_transition(
    from_state: Level52TransitionState,
    to_state: Level52TransitionState,
) -> bool:
    """Return True if direct transition from from_state to to_state is valid in state machine topology."""
    allowed = _VALID_TRANSITIONS.get(from_state)
    if allowed is None:
        return False
    return to_state in allowed


def trigger_transition_start(
    target: Level52TransitionResult | Level52TransitionRecord | Level52TransitionState | str,
    notes: str | None = None,
    triggered_at: str | None = None,
) -> Level52TransitionResult | Level52TransitionRecord | Level52TransitionState:
    """Explicitly trigger transition start event, transitioning from READY to TRANSITIONING.

    Rejects any non-READY state by raising InvalidTransitionError.
    """
    current_state: Level52TransitionState
    if isinstance(target, Level52TransitionResult):
        current_state = target.state
    elif isinstance(target, Level52TransitionRecord):
        current_state = target.state
    elif isinstance(target, Level52TransitionState):
        current_state = target
    elif isinstance(target, str):
        current_state = Level52TransitionState(target)
    else:
        raise InvalidTransitionError(f"Unsupported target type for transition trigger: {type(target)}")

    if current_state != Level52TransitionState.READY:
        raise InvalidTransitionError(
            f"Cannot trigger transition start from state '{current_state}': only READY may transition to TRANSITIONING."
        )

    if isinstance(target, Level52TransitionResult):
        return Level52TransitionResult(
            state=Level52TransitionState.TRANSITIONING,
            character_level=target.character_level,
            requirements=target.requirements,
            blocking_requirements=target.blocking_requirements,
            completion_markers=target.completion_markers,
            unknowns=target.unknowns,
            has_verified_preswap_evidence=target.has_verified_preswap_evidence,
            evaluated_at=triggered_at or target.evaluated_at,
            notes=notes or target.notes,
        )
    elif isinstance(target, Level52TransitionRecord):
        return Level52TransitionRecord(
            state=Level52TransitionState.TRANSITIONING,
            requirements=target.requirements,
            last_evaluated_at=triggered_at or target.last_evaluated_at,
            verified_at=target.verified_at,
            notes=notes or target.notes,
        )
    else:
        return Level52TransitionState.TRANSITIONING


def evaluate_level52_transition(
    character_level: int | None = None,
    current_state: Level52TransitionState | Level52TransitionRecord | Level52TransitionResult | str | None = None,
    delta: BuildDeltaResult | None = None,
    character_state: CharacterState | None = None,
    rules: list[GuideRule] | None = None,
    evidence_map: dict[str, Any] | None = None,
    has_verified_preswap_evidence: bool = False,
    has_verified_completion_evidence: bool | None = None,
    notes: str | None = None,
    evaluated_at: str | None = None,
) -> Level52TransitionResult:
    """Statelessly and deterministically evaluate the Level-52 progression transition milestone.

    Enforces:
    1. level < 52: NOT_RELEVANT unless applicable USABLE PREPARATION rule is satisfied (PREPARING).
    2. level >= 52 with unobserved/stale/insufficient evidence: VERIFYING (never false BLOCKED).
    3. level >= 52 with verified failed USABLE BLOCKING_REQUIREMENT or pre-swap evidence: BLOCKED.
    4. level >= 52 with all applicable USABLE blockers satisfied: READY (pending rules do not deadlock READY).
    5. READY -> TRANSITIONING requires explicit trigger_transition_start (never automatic).
    6. TRANSITIONING -> COMPLETE requires verified post-swap evidence matching USABLE COMPLETION_EVIDENCE rules.
    7. Late install at level >= 52:
       - With verified completion evidence: directly resolves COMPLETE.
       - With verified pre-swap evidence: resolves BLOCKED (with missed_transition=True).
       - With insufficient evidence: resolves VERIFYING (with transition_pending=True, missed_transition=False).
    8. Idempotent COMPLETE: once COMPLETE, subsequent evaluations and level advancements preserve COMPLETE.
    """
    # 1. Resolve and validate character level
    resolved_level = character_level
    if resolved_level is None and character_state is not None:
        resolved_level = _extract_character_level(character_state)
    if resolved_level is None and delta is not None:
        resolved_level = validate_character_level(delta.character_level)
    if resolved_level is None and isinstance(current_state, Level52TransitionResult):
        resolved_level = current_state.character_level

    if resolved_level is None:
        raise InvalidCharacterLevelError(
            "Character level must be provided and valid integer between 1 and 100."
        )
    valid_level = validate_character_level(resolved_level)
    if valid_level is None:
        raise InvalidCharacterLevelError("Character level cannot be None.")

    # 2. Resolve current persistent state
    resolved_current_state: Level52TransitionState | None = None
    if isinstance(current_state, Level52TransitionState):
        resolved_current_state = current_state
    elif isinstance(current_state, Level52TransitionResult):
        resolved_current_state = current_state.state
    elif isinstance(current_state, Level52TransitionRecord):
        resolved_current_state = current_state.state
    elif isinstance(current_state, str):
        resolved_current_state = Level52TransitionState(current_state)
    elif character_state is not None and getattr(character_state, "transition", None) is not None:
        trans_rec = getattr(character_state, "transition")
        if trans_rec is not None:
            resolved_current_state = getattr(trans_rec, "state", None)

    # 3. Resolve pre-swap evidence flag
    is_preswap_active = has_verified_preswap_evidence or bool(
        evidence_map and (
            evidence_map.get("has_verified_preswap_evidence") is True
            or evidence_map.get("preswap_evidence") is True
        )
    )

    # 4. Evaluate guide rules and requirements
    resolved_rules = rules if rules is not None else load_guide_rules()
    evaluations = evaluate_requirements(
        rules=resolved_rules,
        delta=delta,
        character_state=character_state,
        character_level=valid_level,
        evidence_map=evidence_map,
    )

    blocking_requirements = [e for e in evaluations if e.is_applicable_blocker]
    completion_markers = [
        e for e in evaluations
        if e.transition_role == TransitionRuleRole.COMPLETION_EVIDENCE
    ]
    preparation_rules = [
        e for e in evaluations
        if e.transition_role == TransitionRuleRole.PREPARATION
    ]
    unknowns = [e.rule_id for e in evaluations if e.is_unknown]

    # 5. Determine completion evidence satisfaction
    usable_completion = [
        e for e in completion_markers
        if e.source_status == SourceVerificationStatus.USABLE
        and e.eligibility not in (EligibilityState.FUTURE, EligibilityState.EXPIRED)
    ]
    if has_verified_completion_evidence is not None:
        completion_verified = has_verified_completion_evidence
    else:
        completion_verified = bool(
            usable_completion and all(e.is_satisfied for e in usable_completion)
        )

    # 6. State determination logic
    final_state: Level52TransitionState

    # Rule 8: COMPLETE idempotence
    if resolved_current_state == Level52TransitionState.COMPLETE:
        final_state = Level52TransitionState.COMPLETE

    # Rule 1: Level < 52 boundary
    elif valid_level < 52:
        usable_prep = [
            e for e in preparation_rules
            if e.source_status == SourceVerificationStatus.USABLE
            and e.eligibility not in (EligibilityState.FUTURE, EligibilityState.EXPIRED)
        ]
        if any(e.is_satisfied for e in usable_prep):
            final_state = Level52TransitionState.PREPARING
        else:
            final_state = Level52TransitionState.NOT_RELEVANT

    # Level >= 52 logic
    else:
        # Rules 6 & 7: Verified completion evidence
        if completion_verified:
            final_state = Level52TransitionState.COMPLETE

        # If currently TRANSITIONING without completion evidence
        elif resolved_current_state == Level52TransitionState.TRANSITIONING:
            if is_preswap_active or has_unsatisfied_blocker(evaluations):
                final_state = Level52TransitionState.BLOCKED
            else:
                final_state = Level52TransitionState.TRANSITIONING

        # Rule 3 & 7: Verified pre-swap evidence or failed blocker -> BLOCKED
        elif is_preswap_active or has_unsatisfied_blocker(evaluations):
            final_state = Level52TransitionState.BLOCKED

        # Rule 4: All applicable USABLE blockers satisfied -> READY
        elif blocking_requirements and all(e.is_satisfied for e in blocking_requirements):
            final_state = Level52TransitionState.READY

        # If already READY and no blockers failed
        elif resolved_current_state == Level52TransitionState.READY:
            if any(e.is_unknown for e in blocking_requirements):
                final_state = Level52TransitionState.VERIFYING
            else:
                final_state = Level52TransitionState.READY

        # Rule 2 & 7: Incomplete, unobserved, or insufficient evidence -> VERIFYING
        else:
            final_state = Level52TransitionState.VERIFYING

    return Level52TransitionResult(
        state=final_state,
        character_level=valid_level,
        requirements=evaluations,
        blocking_requirements=blocking_requirements,
        completion_markers=completion_markers,
        unknowns=unknowns,
        has_verified_preswap_evidence=is_preswap_active,
        evaluated_at=evaluated_at,
        notes=notes,
    )
