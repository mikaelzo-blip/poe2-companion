"""Unit tests for Level-52 Persistent Transition State Machine and Status Flags.

Tests compliance with Milestone 3 Tasks 4.1, 4.2, 4.3:
- All 7 valid transition states and allowed transitions.
- Rejection of invalid transitions (READY -> TRANSITIONING requires explicit trigger, etc.).
- BLOCKED vs VERIFYING distinction (uncertainty never BLOCKED).
- READY requirements (all applicable USABLE blockers satisfied).
- Late-install direct completion at level 60 with completion evidence.
- Late-install level 60 with verified pre-swap build (BLOCKED + missed_transition = True).
- Late-install level 60 with insufficient evidence (VERIFYING + transition_pending = True + missed_transition = False).
- Level 51 without usable prep rule (NOT_RELEVANT) vs with usable prep rule (PREPARING).
- Level 51 with pending prep rule (NOT_RELEVANT).
- Explicit transition start signal trigger_transition_start.
- COMPLETE idempotence across level advancement (52 -> 58+).
"""

from __future__ import annotations

import pytest

from companion.build.conflicts import ConflictRecord
from companion.build.delta import BuildDeltaResult
from companion.build.eligibility import EligibilityState
from companion.build.equipment import EquipmentDeltaEntry
from companion.build.passives import PassiveDeltaEntry
from companion.build.policy import DeltaReason, DeltaStatus
from companion.build.skills import SkillGroupDeltaEntry
from companion.build.validation import InvalidCharacterLevelError
from companion.rules.schema import (
    GuideRule,
    ObservabilityMethod,
    RequirementType,
    RuleEvaluationState,
    RuleSourceType,
    SourceVerificationStatus,
    TransitionRuleRole,
)
from companion.sources.interval import LevelInterval
from companion.transition.evaluator import (
    InvalidTransitionError,
    can_transition,
    evaluate_level52_transition,
    trigger_transition_start,
)
from companion.transition.requirements import (
    RequirementEvaluation,
    RequirementReadiness,
    evaluate_requirements,
)
from companion.transition.state import (
    Level52TransitionRecord,
    Level52TransitionResult,
    Level52TransitionState,
)


# ==============================================================================
# 1. State Enum & Result Model Property Tests (Task 4.1)
# ==============================================================================


def test_transition_states_enum_values() -> None:
    """Verify Level52TransitionState contains exactly the 7 canonical persistent states."""
    expected_states = {
        "NOT_RELEVANT",
        "PREPARING",
        "VERIFYING",
        "BLOCKED",
        "READY",
        "TRANSITIONING",
        "COMPLETE",
    }
    actual_states = {s.value for s in Level52TransitionState}
    assert actual_states == expected_states
    assert len(Level52TransitionState) == 7


def test_level52_transition_result_model_structure() -> None:
    """Verify Level52TransitionResult fields, defaults, and immutability."""
    res = Level52TransitionResult(
        state=Level52TransitionState.VERIFYING,
        character_level=52,
        unknowns=["REQ_1"],
        evaluated_at="2026-03-31T12:00:00Z",
        notes="Audit incomplete",
    )
    assert res.state == Level52TransitionState.VERIFYING
    assert res.character_level == 52
    assert res.requirements == []
    assert res.blocking_requirements == []
    assert res.completion_markers == []
    assert res.unknowns == ["REQ_1"]
    assert res.has_verified_preswap_evidence is False
    assert res.evaluated_at == "2026-03-31T12:00:00Z"
    assert res.notes == "Audit incomplete"

    # Immutability
    with pytest.raises(Exception):
        res.state = Level52TransitionState.READY  # type: ignore[misc]


def test_transition_pending_derived_property() -> None:
    """Verify transition_pending is deterministically derived as level > 52 and state != COMPLETE."""
    # level <= 52 is never pending
    r1 = Level52TransitionResult(state=Level52TransitionState.VERIFYING, character_level=52)
    assert r1.transition_pending is False

    r2 = Level52TransitionResult(state=Level52TransitionState.BLOCKED, character_level=51)
    assert r2.transition_pending is False

    # level > 52 and state != COMPLETE is pending
    r3 = Level52TransitionResult(state=Level52TransitionState.VERIFYING, character_level=53)
    assert r3.transition_pending is True

    r4 = Level52TransitionResult(state=Level52TransitionState.BLOCKED, character_level=60)
    assert r4.transition_pending is True

    r5 = Level52TransitionResult(state=Level52TransitionState.READY, character_level=55)
    assert r5.transition_pending is True

    r6 = Level52TransitionResult(state=Level52TransitionState.TRANSITIONING, character_level=54)
    assert r6.transition_pending is True

    # Once COMPLETE, transition_pending is strictly False
    r7 = Level52TransitionResult(state=Level52TransitionState.COMPLETE, character_level=53)
    assert r7.transition_pending is False

    r8 = Level52TransitionResult(state=Level52TransitionState.COMPLETE, character_level=60)
    assert r8.transition_pending is False


def test_missed_transition_derived_property() -> None:
    """Verify missed_transition is deterministically derived as:
    level > 52 and state != COMPLETE and has_verified_preswap_evidence.
    """
    # level <= 52 -> False
    r1 = Level52TransitionResult(
        state=Level52TransitionState.BLOCKED,
        character_level=52,
        has_verified_preswap_evidence=True,
    )
    assert r1.missed_transition is False

    # level > 52 but no preswap evidence -> False
    r2 = Level52TransitionResult(
        state=Level52TransitionState.BLOCKED,
        character_level=53,
        has_verified_preswap_evidence=False,
    )
    assert r2.missed_transition is False

    # level > 52, not COMPLETE, with verified preswap evidence -> True
    r3 = Level52TransitionResult(
        state=Level52TransitionState.BLOCKED,
        character_level=53,
        has_verified_preswap_evidence=True,
    )
    assert r3.missed_transition is True

    r4 = Level52TransitionResult(
        state=Level52TransitionState.VERIFYING,
        character_level=60,
        has_verified_preswap_evidence=True,
    )
    assert r4.missed_transition is True

    # Once COMPLETE, missed_transition is strictly False even if has_verified_preswap_evidence is True
    r5 = Level52TransitionResult(
        state=Level52TransitionState.COMPLETE,
        character_level=60,
        has_verified_preswap_evidence=True,
    )
    assert r5.missed_transition is False


def test_level52_transition_record_conversion() -> None:
    """Verify Level52TransitionRecord conversion from Level52TransitionResult."""
    req_eval = RequirementEvaluation(
        rule_id="SWAP_STAFF",
        rule_name="Equip Staff",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        readiness=RequirementReadiness.SATISFIED,
    )
    result = Level52TransitionResult(
        state=Level52TransitionState.READY,
        character_level=52,
        requirements=[req_eval],
        evaluated_at="2026-03-31T12:00:00Z",
        notes="Ready for swap",
    )
    record = result.to_record()
    assert isinstance(record, Level52TransitionRecord)
    assert record.state == Level52TransitionState.READY
    assert record.requirements == {"SWAP_STAFF": RequirementReadiness.SATISFIED}
    assert record.last_evaluated_at == "2026-03-31T12:00:00Z"
    assert record.notes == "Ready for swap"


# ==============================================================================
# 2. Pre-52 Evaluation Tests: PREPARING vs NOT_RELEVANT (Task 4.2)
# ==============================================================================


def test_level_below_52_without_usable_prep_rule_evaluates_not_relevant() -> None:
    """Verify level < 52 without an applicable USABLE preparation rule is NOT_RELEVANT.

    Ensures no invented preparation thresholds (45, 50, 51).
    """
    for lvl in [1, 20, 45, 50, 51]:
        res = evaluate_level52_transition(character_level=lvl)
        assert res.state == Level52TransitionState.NOT_RELEVANT
        assert res.character_level == lvl
        assert res.transition_pending is False
        assert res.missed_transition is False


def test_level_below_52_with_usable_prep_rule_satisfied_evaluates_preparing() -> None:
    """Verify level < 52 with an applicable USABLE PREPARATION rule satisfied evaluates to PREPARING."""
    usable_prep_rule = GuideRule(
        id="PREP_WEAPON_BASES",
        name="Acquire Level 52 Weapon Bases",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.PREPARATION,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=45,
        max_level=51,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res = evaluate_level52_transition(
        character_level=51,
        rules=[usable_prep_rule],
        evidence_map={"PREP_WEAPON_BASES": True},
    )
    assert res.state == Level52TransitionState.PREPARING
    assert res.character_level == 51
    assert res.transition_pending is False
    assert res.missed_transition is False


def test_level_below_52_with_pending_source_prep_rule_evaluates_not_relevant() -> None:
    """Verify PENDING_SOURCE_VERIFICATION preparation rule cannot trigger PREPARING authoritatively."""
    pending_prep_rule = GuideRule(
        id="FUBGUN_WRITTEN_GUIDE_GEAR_PRIORITIES",
        name="Fubgun Written Guide Gear Priorities",
        source_status=SourceVerificationStatus.PENDING_SOURCE_VERIFICATION,
        transition_role=TransitionRuleRole.PREPARATION,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=33,
        max_level=51,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res = evaluate_level52_transition(
        character_level=51,
        rules=[pending_prep_rule],
        evidence_map={"FUBGUN_WRITTEN_GUIDE_GEAR_PRIORITIES": True},
    )
    assert res.state == Level52TransitionState.NOT_RELEVANT
    assert res.character_level == 51
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# 3. Level 52 Evaluation: VERIFYING vs BLOCKED vs READY (Task 4.2)
# ==============================================================================


def test_level_52_no_evidence_evaluates_verifying() -> None:
    """Verify level >= 52 with no observations evaluates to VERIFYING (never false BLOCKED)."""
    res = evaluate_level52_transition(character_level=52)
    assert res.state == Level52TransitionState.VERIFYING
    assert res.character_level == 52
    assert res.transition_pending is False
    assert res.missed_transition is False


def test_level_52_stale_or_unobserved_evidence_evaluates_verifying_never_blocked() -> None:
    """Verify stale or incomplete observations evaluate to VERIFYING, never BLOCKED."""
    blocker_rule = GuideRule(
        id="SWAP_STAFF",
        name="Equip Staff",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    stale_evidence = EquipmentDeltaEntry(
        slot_id="weapon",
        item_name="Quarterstaff",
        status=DeltaStatus.UNKNOWN,
        reason=DeltaReason.STALE_PLAYER_STATE,
    )
    res = evaluate_level52_transition(
        character_level=52,
        rules=[blocker_rule],
        evidence_map={"SWAP_STAFF": stale_evidence},
    )
    assert res.state == Level52TransitionState.VERIFYING
    assert res.character_level == 52
    assert "SWAP_STAFF" in res.unknowns


def test_level_52_verified_failed_usable_blocker_evaluates_blocked() -> None:
    """Verify verified failed USABLE blocking requirement evaluates to BLOCKED."""
    blocker_rule = GuideRule(
        id="SWAP_STAFF",
        name="Equip Staff",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    missing_evidence = EquipmentDeltaEntry(
        slot_id="weapon",
        item_name=None,
        status=DeltaStatus.MISSING,
        reason=DeltaReason.NONE,
    )
    res = evaluate_level52_transition(
        character_level=52,
        rules=[blocker_rule],
        evidence_map={"SWAP_STAFF": missing_evidence},
    )
    assert res.state == Level52TransitionState.BLOCKED
    assert res.character_level == 52
    assert len(res.blocking_requirements) == 1
    assert res.blocking_requirements[0].is_unsatisfied is True


def test_level_52_all_applicable_usable_blockers_satisfied_evaluates_ready() -> None:
    """Verify level 52 with all applicable USABLE blockers satisfied evaluates to READY."""
    blocker_rule = GuideRule(
        id="SWAP_STAFF",
        name="Equip Staff",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    cod_rule = GuideRule(
        id="GEM_CAST_ON_DODGE",
        name="Cast on Dodge Meta-Gem",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.SKILL,
        min_level=58,
        observable_via=[ObservabilityMethod.SKILL_AUDIT],
    )
    cod_evidence = SkillGroupDeltaEntry(
        logical_key=("CastOnDodge", None),
        primary_gem_id="CastOnDodge",
        status=DeltaStatus.FUTURE,
        reason=DeltaReason.INELIGIBLE_LEVEL,
        level_interval=LevelInterval(kind="RANGE", min_level=58, max_level=100),
    )
    res = evaluate_level52_transition(
        character_level=52,
        rules=[blocker_rule, cod_rule],
        evidence_map={
            "SWAP_STAFF": True,
            "GEM_CAST_ON_DODGE": cod_evidence,
        },
    )
    assert res.state == Level52TransitionState.READY
    assert res.character_level == 52
    assert len(res.blocking_requirements) == 1
    assert res.blocking_requirements[0].rule_id == "SWAP_STAFF"
    assert res.blocking_requirements[0].is_satisfied is True


def test_pending_source_verification_rule_does_not_deadlock_ready() -> None:
    """Verify PENDING_SOURCE_VERIFICATION rule does not prevent READY when all usable blockers pass."""
    blocker_rule = GuideRule(
        id="SWAP_STAFF",
        name="Equip Staff",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    pending_rule = GuideRule(
        id="EXTERNAL_UNVERIFIED_RULE",
        name="Unverified External Rule",
        source_status=SourceVerificationStatus.PENDING_SOURCE_VERIFICATION,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res = evaluate_level52_transition(
        character_level=52,
        rules=[blocker_rule, pending_rule],
        evidence_map={
            "SWAP_STAFF": True,
            "EXTERNAL_UNVERIFIED_RULE": None,
        },
    )
    assert res.state == Level52TransitionState.READY
    assert res.character_level == 52


# ==============================================================================
# 4. Explicit Trigger & Invalid Transition Rejections (Task 4.2, 4.3)
# ==============================================================================


def test_ready_cannot_become_transitioning_without_explicit_trigger() -> None:
    """Verify evaluate_level52_transition never automatically advances READY to TRANSITIONING."""
    blocker_rule = GuideRule(
        id="SWAP_STAFF",
        name="Equip Staff",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res = evaluate_level52_transition(
        character_level=52,
        current_state=Level52TransitionState.READY,
        rules=[blocker_rule],
        evidence_map={"SWAP_STAFF": True},
    )
    assert res.state == Level52TransitionState.READY


def test_trigger_transition_start_moves_ready_to_transitioning() -> None:
    """Verify trigger_transition_start moves READY state to TRANSITIONING."""
    ready_result = Level52TransitionResult(
        state=Level52TransitionState.READY,
        character_level=52,
    )
    transitioning_result = trigger_transition_start(ready_result)
    assert isinstance(transitioning_result, Level52TransitionResult)
    assert transitioning_result.state == Level52TransitionState.TRANSITIONING
    assert transitioning_result.character_level == 52

    # Also test with Level52TransitionRecord
    ready_record = Level52TransitionRecord(state=Level52TransitionState.READY)
    transitioning_record = trigger_transition_start(ready_record)
    assert isinstance(transitioning_record, Level52TransitionRecord)
    assert transitioning_record.state == Level52TransitionState.TRANSITIONING

    # Also test with raw enum
    transitioning_enum = trigger_transition_start(Level52TransitionState.READY)
    assert transitioning_enum == Level52TransitionState.TRANSITIONING


def test_trigger_transition_start_rejects_non_ready_states() -> None:
    """Verify trigger_transition_start raises InvalidTransitionError from any non-READY state."""
    non_ready_states = [
        Level52TransitionState.NOT_RELEVANT,
        Level52TransitionState.PREPARING,
        Level52TransitionState.VERIFYING,
        Level52TransitionState.BLOCKED,
        Level52TransitionState.TRANSITIONING,
        Level52TransitionState.COMPLETE,
    ]
    for st in non_ready_states:
        res = Level52TransitionResult(state=st, character_level=52)
        with pytest.raises(InvalidTransitionError):
            trigger_transition_start(res)

        rec = Level52TransitionRecord(state=st)
        with pytest.raises(InvalidTransitionError):
            trigger_transition_start(rec)

        with pytest.raises(InvalidTransitionError):
            trigger_transition_start(st)


def test_transitioning_to_complete_requires_verified_completion_evidence() -> None:
    """Verify TRANSITIONING state moves to COMPLETE only with verified completion evidence."""
    completion_rule = GuideRule(
        id="SWAP_LVL_52",
        name="Level 52 Weapon Swap",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.COMPLETION_EVIDENCE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    # 1. TRANSITIONING with completion evidence unobserved -> stays TRANSITIONING
    res1 = evaluate_level52_transition(
        character_level=52,
        current_state=Level52TransitionState.TRANSITIONING,
        rules=[completion_rule],
        evidence_map={"SWAP_LVL_52": None},
    )
    assert res1.state == Level52TransitionState.TRANSITIONING

    # 2. TRANSITIONING with verified completion evidence -> moves to COMPLETE
    res2 = evaluate_level52_transition(
        character_level=52,
        current_state=Level52TransitionState.TRANSITIONING,
        rules=[completion_rule],
        evidence_map={"SWAP_LVL_52": True},
    )
    assert res2.state == Level52TransitionState.COMPLETE
    assert res2.transition_pending is False
    assert res2.missed_transition is False


def test_can_transition_matrix() -> None:
    """Verify can_transition helper adheres to transition state machine topology."""
    # From COMPLETE: only COMPLETE is allowed
    assert can_transition(Level52TransitionState.COMPLETE, Level52TransitionState.COMPLETE) is True
    assert can_transition(Level52TransitionState.COMPLETE, Level52TransitionState.VERIFYING) is False
    assert can_transition(Level52TransitionState.COMPLETE, Level52TransitionState.READY) is False
    assert can_transition(Level52TransitionState.COMPLETE, Level52TransitionState.BLOCKED) is False

    # To TRANSITIONING: only from READY is allowed
    assert can_transition(Level52TransitionState.READY, Level52TransitionState.TRANSITIONING) is True
    assert can_transition(Level52TransitionState.VERIFYING, Level52TransitionState.TRANSITIONING) is False
    assert can_transition(Level52TransitionState.BLOCKED, Level52TransitionState.TRANSITIONING) is False
    assert can_transition(Level52TransitionState.NOT_RELEVANT, Level52TransitionState.TRANSITIONING) is False


# ==============================================================================
# 5. Late Installation & Recovery Scenarios (Task 4.2, 4.3)
# ==============================================================================


def test_late_install_level_60_with_completion_evidence_resolves_complete() -> None:
    """Verify late install at level 60 with verified completion evidence resolves to COMPLETE."""
    completion_rule = GuideRule(
        id="SWAP_LVL_52",
        name="Level 52 Weapon Swap",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.COMPLETION_EVIDENCE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res = evaluate_level52_transition(
        character_level=60,
        rules=[completion_rule],
        evidence_map={"SWAP_LVL_52": True},
    )
    assert res.state == Level52TransitionState.COMPLETE
    assert res.character_level == 60
    assert res.transition_pending is False
    assert res.missed_transition is False


def test_late_install_level_60_with_verified_preswap_build_resolves_blocked_missed() -> None:
    """Verify late install at level 60 with verified pre-swap build resolves BLOCKED + missed_transition."""
    res = evaluate_level52_transition(
        character_level=60,
        has_verified_preswap_evidence=True,
    )
    assert res.state == Level52TransitionState.BLOCKED
    assert res.character_level == 60
    assert res.transition_pending is True
    assert res.missed_transition is True


def test_late_install_level_60_with_insufficient_evidence_resolves_verifying() -> None:
    """Verify late install at level 60 with insufficient evidence resolves to VERIFYING (not false BLOCKED)."""
    res = evaluate_level52_transition(
        character_level=60,
        has_verified_preswap_evidence=False,
    )
    assert res.state == Level52TransitionState.VERIFYING
    assert res.character_level == 60
    assert res.transition_pending is True
    assert res.missed_transition is False


# ==============================================================================
# 6. Idempotence & Progression Advancement (Task 4.2, 4.3)
# ==============================================================================


def test_complete_state_is_idempotent_across_level_advancement() -> None:
    """Verify once COMPLETE, level advancement to 58+ preserves COMPLETE without reopening."""
    # Character completed at level 52
    res_lvl52 = Level52TransitionResult(
        state=Level52TransitionState.COMPLETE,
        character_level=52,
    )
    # Character advances to level 58 where Cast on Dodge becomes active and missing
    cod_rule = GuideRule(
        id="GEM_CAST_ON_DODGE",
        name="Cast on Dodge",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.SKILL,
        min_level=58,
        observable_via=[ObservabilityMethod.SKILL_AUDIT],
    )
    res_lvl58 = evaluate_level52_transition(
        character_level=58,
        current_state=res_lvl52,
        rules=[cod_rule],
        evidence_map={"GEM_CAST_ON_DODGE": False},
    )
    assert res_lvl58.state == Level52TransitionState.COMPLETE
    assert res_lvl58.character_level == 58
    assert res_lvl58.transition_pending is False
    assert res_lvl58.missed_transition is False


def test_invalid_character_level_raises_error() -> None:
    """Verify invalid character levels (<= 0, > 100, non-int) raise InvalidCharacterLevelError."""
    with pytest.raises(InvalidCharacterLevelError):
        evaluate_level52_transition(character_level=0)

    with pytest.raises(InvalidCharacterLevelError):
        evaluate_level52_transition(character_level=101)

    with pytest.raises(InvalidCharacterLevelError):
        evaluate_level52_transition(character_level=-5)


def test_level_below_52_never_evaluates_complete_even_with_completion_evidence() -> None:
    """Verify level < 52 strictly evaluates to NOT_RELEVANT/PREPARING, never COMPLETE."""
    completion_rule = GuideRule(
        id="SWAP_LVL_52",
        name="Level 52 Weapon Swap",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.COMPLETION_EVIDENCE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res = evaluate_level52_transition(
        character_level=51,
        rules=[completion_rule],
        evidence_map={"SWAP_LVL_52": True},
        has_verified_completion_evidence=True,
    )
    assert res.state == Level52TransitionState.NOT_RELEVANT
    assert res.character_level == 51
    assert res.transition_pending is False
    assert res.missed_transition is False


def test_late_install_level_60_evolved_build_retaining_markers_resolves_complete() -> None:
    """Verify level 60 evolved build differing from lvl52 snapshot resolves COMPLETE."""
    completion_rule = GuideRule(
        id="SWAP_LVL_52",
        name="Level 52 Weapon Swap",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.COMPLETION_EVIDENCE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res = evaluate_level52_transition(
        character_level=60,
        rules=[completion_rule],
        evidence_map={"SWAP_LVL_52": True},
        notes="Evolved Endgame variant",
    )
    assert res.state == Level52TransitionState.COMPLETE
    assert res.character_level == 60
    assert res.transition_pending is False
    assert res.missed_transition is False


def test_state_evaluation_is_deterministic() -> None:
    """Verify identical inputs produce identical Level52TransitionResult."""
    res1 = evaluate_level52_transition(
        character_level=52,
        has_verified_preswap_evidence=False,
        evaluated_at="2026-03-31T12:00:00Z",
    )
    res2 = evaluate_level52_transition(
        character_level=52,
        has_verified_preswap_evidence=False,
        evaluated_at="2026-03-31T12:00:00Z",
    )
    assert res1 == res2

