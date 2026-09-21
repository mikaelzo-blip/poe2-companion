"""Comprehensive golden scenario test suite for Milestone 3 Level-52 Transition.

Explicitly tests all 26 canonical golden scenarios:
1.  Level 51 pre-transition without usable preparation rule (NOT_RELEVANT)
2.  Level 51 with usable PREPARATION rule satisfied/applicable (PREPARING)
3.  PENDING_SOURCE_VERIFICATION preparation rule does not trigger PREPARING authoritatively (NOT_RELEVANT)
4.  PENDING_SOURCE_VERIFICATION blocking rule cannot create BLOCKED
5.  PENDING_SOURCE_VERIFICATION rule does not permanently deadlock or prevent READY when all usable blockers pass
6.  Level 52 with no observations (VERIFYING)
7.  Level 52 with partial observations (VERIFYING)
8.  Level 52 with stale observations (VERIFYING)
9.  Level 52 with one verified failed usable blocker (BLOCKED)
10. Level 52 with all currently applicable usable blockers satisfied (READY)
11. Level 52 with Cast on Dodge FUTURE (evaluates READY)
12. Level 53 incomplete (transition_pending = True, VERIFYING or BLOCKED)
13. Level 58 advancement where Cast on Dodge becomes ACTIVE (level-52 transition remains COMPLETE)
14. Level 60 late install with exact historical post-swap evidence (COMPLETE, missed_transition = False)
15. Level 60 evolved build with sufficient completion markers (COMPLETE, missed_transition = False)
16. Level 60 with verified pre-swap build (BLOCKED, missed_transition = True)
17. Level 60 current build differs from lvl52 snapshot and evidence insufficient (VERIFYING, transition_pending = True, missed_transition = False)
18. Skill weapon-set inference is not used for completion
19. Migrated 2.0 state at level 20 has transition = None, first evaluation initializes to NOT_RELEVANT
20. Migrated 2.0 state at level 52 has transition = None, first evaluation initializes to VERIFYING
21. Migrated 2.0 state at level 60 with completion evidence has transition = None, first evaluation initializes to COMPLETE
22. Restart while VERIFYING preserves state
23. Restart while BLOCKED preserves state
24. Restart while READY preserves state
25. Restart while COMPLETE preserves state
26. Conflicting source/evidence yields CONFLICTING_EVIDENCE
"""

from __future__ import annotations

from pathlib import Path
import pytest

from companion.build.conflicts import ConflictRecord
from companion.build.delta import BuildDeltaResult
from companion.build.eligibility import EligibilityState
from companion.build.equipment import EquipmentDeltaEntry
from companion.build.passives import PassiveDeltaEntry
from companion.build.policy import DeltaReason, DeltaStatus
from companion.build.progression import ProgressionPhase
from companion.build.skills import SkillGroupDeltaEntry
from companion.build.variants import TargetVariantResolution, VariantResolutionStatus
from companion.rules.evaluator import RuleEvidence, evaluate_rule
from companion.rules.loader import load_guide_rules
from companion.rules.schema import (
    GuideRule,
    ObservabilityMethod,
    RequirementType,
    RuleEvaluationState,
    RuleSourceType,
    SourceVerificationStatus,
    TransitionRuleRole,
)
from companion.sources.interval import IntervalKind, LevelInterval
from companion.sources.models_normalized import WeaponSetContext
from companion.state.provenance import ProvenancedField, VerificationState
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore
from companion.transition.evaluator import (
    evaluate_level52_transition,
    trigger_transition_start,
)
from companion.transition.requirements import (
    RequirementEvaluation,
    RequirementReadiness,
    evaluate_requirements,
    evaluate_single_requirement,
)
from companion.transition.state import (
    Level52TransitionRecord,
    Level52TransitionResult,
    Level52TransitionState,
)


# ==============================================================================
# Scenario 1: Level 51 pre-transition without usable preparation rule (NOT_RELEVANT)
# ==============================================================================
def test_golden_01_level_51_pre_transition_without_usable_prep_rule() -> None:
    """Level 51 pre-transition without usable preparation rule evaluates to NOT_RELEVANT."""
    res = evaluate_level52_transition(character_level=51)
    assert res.state == Level52TransitionState.NOT_RELEVANT
    assert res.character_level == 51
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# Scenario 2: Level 51 with usable PREPARATION rule satisfied/applicable (PREPARING)
# ==============================================================================
def test_golden_02_level_51_with_usable_prep_rule_satisfied_evaluates_preparing() -> None:
    """Level 51 with usable PREPARATION rule satisfied/applicable evaluates to PREPARING."""
    usable_prep_rule = GuideRule(
        id="PREP_WEAPON_BASES",
        name="Acquire Level 52 Weapon Bases",
        provenance=RuleSourceType.BLUEPRINT_V2,
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


# ==============================================================================
# Scenario 3: PENDING_SOURCE_VERIFICATION preparation rule does not trigger PREPARING (NOT_RELEVANT)
# ==============================================================================
def test_golden_03_pending_source_prep_rule_does_not_trigger_preparing() -> None:
    """PENDING_SOURCE_VERIFICATION preparation rule does not trigger PREPARING authoritatively (NOT_RELEVANT)."""
    pending_prep_rule = GuideRule(
        id="FUBGUN_WRITTEN_GUIDE_GEAR_PRIORITIES",
        name="Fubgun Written Guide Gear Priorities",
        provenance=RuleSourceType.PENDING_SOURCE_VERIFICATION,
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
# Scenario 4: PENDING_SOURCE_VERIFICATION blocking rule cannot create BLOCKED
# ==============================================================================
def test_golden_04_pending_source_blocking_rule_cannot_create_blocked() -> None:
    """PENDING_SOURCE_VERIFICATION blocking rule cannot create BLOCKED."""
    pending_blocker = GuideRule(
        id="UNVERIFIED_GUIDE_BLOCKER",
        name="Unverified External Blocker",
        provenance=RuleSourceType.PENDING_SOURCE_VERIFICATION,
        source_status=SourceVerificationStatus.PENDING_SOURCE_VERIFICATION,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    # Evidence indicates failure, but rule is PENDING_SOURCE_VERIFICATION
    res = evaluate_level52_transition(
        character_level=52,
        rules=[pending_blocker],
        evidence_map={"UNVERIFIED_GUIDE_BLOCKER": False},
    )
    assert res.state != Level52TransitionState.BLOCKED
    assert res.state == Level52TransitionState.VERIFYING
    assert res.transition_pending is False


# ==============================================================================
# Scenario 5: PENDING_SOURCE_VERIFICATION rule does not deadlock or prevent READY
# ==============================================================================
def test_golden_05_pending_source_rule_does_not_deadlock_ready() -> None:
    """PENDING_SOURCE_VERIFICATION rule does not permanently deadlock or prevent READY when all usable blockers pass."""
    usable_blocker = GuideRule(
        id="USABLE_BLOCKER_GEM",
        name="Equip Required Main Gem",
        provenance=RuleSourceType.BLUEPRINT_V2,
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.SKILL,
        min_level=52,
        observable_via=[ObservabilityMethod.SKILL_AUDIT],
    )
    pending_blocker = GuideRule(
        id="PENDING_GUIDE_OFFHAND",
        name="Unverified Offhand Requirement",
        provenance=RuleSourceType.PENDING_SOURCE_VERIFICATION,
        source_status=SourceVerificationStatus.PENDING_SOURCE_VERIFICATION,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res = evaluate_level52_transition(
        character_level=52,
        rules=[usable_blocker, pending_blocker],
        evidence_map={
            "USABLE_BLOCKER_GEM": True,
            "PENDING_GUIDE_OFFHAND": False,  # Pending rule fails or unknown
        },
    )
    # All USABLE blockers pass -> state must be READY, not deadlocked in VERIFYING or BLOCKED
    assert res.state == Level52TransitionState.READY
    assert res.character_level == 52
    assert res.transition_pending is False


# ==============================================================================
# Scenario 6: Level 52 with no observations (VERIFYING)
# ==============================================================================
def test_golden_06_level_52_with_no_observations_is_verifying() -> None:
    """Level 52 with no observations evaluates to VERIFYING (not false BLOCKED)."""
    res = evaluate_level52_transition(
        character_level=52,
        evidence_map={},
        has_verified_preswap_evidence=False,
    )
    assert res.state == Level52TransitionState.VERIFYING
    assert res.character_level == 52
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# Scenario 7: Level 52 with partial observations (VERIFYING)
# ==============================================================================
def test_golden_07_level_52_with_partial_observations_is_verifying() -> None:
    """Level 52 with partial observations evaluates to VERIFYING."""
    blocker_1 = GuideRule(
        id="BLOCKER_1",
        name="Primary Weapon",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    blocker_2 = GuideRule(
        id="BLOCKER_2",
        name="Secondary Weapon",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    # Blocker 1 is observed and satisfied; Blocker 2 is unobserved (None)
    res = evaluate_level52_transition(
        character_level=52,
        rules=[blocker_1, blocker_2],
        evidence_map={"BLOCKER_1": True, "BLOCKER_2": None},
    )
    assert res.state == Level52TransitionState.VERIFYING
    assert res.character_level == 52
    assert res.transition_pending is False


# ==============================================================================
# Scenario 8: Level 52 with stale observations (VERIFYING)
# ==============================================================================
def test_golden_08_level_52_with_stale_observations_is_verifying() -> None:
    """Level 52 with stale observations evaluates to VERIFYING (never false BLOCKED)."""
    blocker = GuideRule(
        id="BLOCKER_SWAP",
        name="Dual Weapon Swap",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    stale_evidence = RuleEvidence(is_stale=True, satisfied=False)
    res = evaluate_level52_transition(
        character_level=52,
        rules=[blocker],
        evidence_map={"BLOCKER_SWAP": stale_evidence},
    )
    assert res.state == Level52TransitionState.VERIFYING
    assert res.character_level == 52
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# Scenario 9: Level 52 with one verified failed usable blocker (BLOCKED)
# ==============================================================================
def test_golden_09_level_52_with_one_verified_failed_usable_blocker_is_blocked() -> None:
    """Level 52 with one verified failed usable blocker evaluates to BLOCKED."""
    blocker_pass = GuideRule(
        id="BLOCKER_PASS",
        name="Passing Blocker",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    blocker_fail = GuideRule(
        id="BLOCKER_FAIL",
        name="Failing Blocker",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.SKILL,
        min_level=52,
        observable_via=[ObservabilityMethod.SKILL_AUDIT],
    )
    res = evaluate_level52_transition(
        character_level=52,
        rules=[blocker_pass, blocker_fail],
        evidence_map={"BLOCKER_PASS": True, "BLOCKER_FAIL": False},
    )
    assert res.state == Level52TransitionState.BLOCKED
    assert res.character_level == 52
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# Scenario 10: Level 52 with all applicable usable blockers satisfied (READY)
# ==============================================================================
def test_golden_10_level_52_with_all_applicable_usable_blockers_satisfied_is_ready() -> None:
    """Level 52 with all currently applicable usable blockers satisfied evaluates to READY."""
    blocker_1 = GuideRule(
        id="BLOCKER_1",
        name="Staff Equipped",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    blocker_2 = GuideRule(
        id="BLOCKER_2",
        name="Gems Slotted",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.SKILL,
        min_level=52,
        observable_via=[ObservabilityMethod.SKILL_AUDIT],
    )
    res = evaluate_level52_transition(
        character_level=52,
        rules=[blocker_1, blocker_2],
        evidence_map={"BLOCKER_1": True, "BLOCKER_2": True},
    )
    assert res.state == Level52TransitionState.READY
    assert res.character_level == 52
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# Scenario 11: Level 52 with Cast on Dodge FUTURE (evaluates READY)
# ==============================================================================
def test_golden_11_level_52_with_cast_on_dodge_future_evaluates_ready() -> None:
    """Level 52 with Cast on Dodge FUTURE evaluates to READY (not blocked by future requirement)."""
    gear_rule = GuideRule(
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
        name="Cast on Dodge",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.SKILL,
        min_level=58,
        observable_via=[ObservabilityMethod.SKILL_AUDIT],
    )
    res = evaluate_level52_transition(
        character_level=52,
        rules=[gear_rule, cod_rule],
        evidence_map={
            "SWAP_STAFF": True,
            "GEM_CAST_ON_DODGE": False,  # Missing from audit, but FUTURE at level 52
        },
    )
    assert res.state == Level52TransitionState.READY
    assert res.character_level == 52
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# Scenario 12: Level 53 incomplete (transition_pending = True, VERIFYING or BLOCKED)
# ==============================================================================
def test_golden_12_level_53_incomplete_has_transition_pending_true() -> None:
    """Level 53 incomplete evaluates with transition_pending = True in VERIFYING or BLOCKED."""
    # Case A: Incomplete with unobserved evidence -> VERIFYING
    res_verifying = evaluate_level52_transition(
        character_level=53,
        evidence_map={},
        has_verified_preswap_evidence=False,
    )
    assert res_verifying.state == Level52TransitionState.VERIFYING
    assert res_verifying.character_level == 53
    assert res_verifying.transition_pending is True
    assert res_verifying.missed_transition is False

    # Case B: Incomplete with failed usable blocker -> BLOCKED
    failed_blocker = GuideRule(
        id="BLOCKER_FAIL",
        name="Failing Blocker",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res_blocked = evaluate_level52_transition(
        character_level=53,
        rules=[failed_blocker],
        evidence_map={"BLOCKER_FAIL": False},
    )
    assert res_blocked.state == Level52TransitionState.BLOCKED
    assert res_blocked.character_level == 53
    assert res_blocked.transition_pending is True


# ==============================================================================
# Scenario 13: Level 58 advancement where Cast on Dodge becomes ACTIVE (COMPLETE preserved)
# ==============================================================================
def test_golden_13_level_58_advancement_cast_on_dodge_active_complete_preserved() -> None:
    """Level 58 advancement where Cast on Dodge becomes ACTIVE leaves level-52 transition COMPLETE."""
    prior_complete_record = Level52TransitionRecord(
        state=Level52TransitionState.COMPLETE,
        verified_at="2026-03-31T12:00:00Z",
    )
    cod_rule = GuideRule(
        id="GEM_CAST_ON_DODGE",
        name="Cast on Dodge",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.SKILL,
        min_level=58,
        observable_via=[ObservabilityMethod.SKILL_AUDIT],
    )
    # Character advances to level 58, Cast on Dodge is missing from player audit
    res = evaluate_level52_transition(
        character_level=58,
        current_state=prior_complete_record,
        rules=[cod_rule],
        evidence_map={"GEM_CAST_ON_DODGE": False},
    )
    assert res.state == Level52TransitionState.COMPLETE
    assert res.character_level == 58
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# Scenario 14: Level 60 late install with exact historical post-swap evidence (COMPLETE)
# ==============================================================================
def test_golden_14_level_60_late_install_exact_historical_post_swap_complete() -> None:
    """Level 60 late install with exact historical post-swap evidence evaluates to COMPLETE."""
    completion_rule = GuideRule(
        id="SWAP_LVL_52",
        name="Level 52 Weapon Swap Milestone",
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
        has_verified_preswap_evidence=False,
    )
    assert res.state == Level52TransitionState.COMPLETE
    assert res.character_level == 60
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# Scenario 15: Level 60 evolved build with sufficient completion markers (COMPLETE)
# ==============================================================================
def test_golden_15_level_60_evolved_build_sufficient_completion_markers_complete() -> None:
    """Level 60 evolved build with sufficient completion markers evaluates to COMPLETE."""
    completion_rule = GuideRule(
        id="SWAP_LVL_52",
        name="Level 52 Weapon Swap Milestone",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.COMPLETION_EVIDENCE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    # Character has evolved gear beyond lvl 52 snapshot, but retains dual weapon set swap evidence
    res = evaluate_level52_transition(
        character_level=60,
        rules=[completion_rule],
        evidence_map={"SWAP_LVL_52": True},
        notes="Evolved to Endgame variant with high-tier gear",
    )
    assert res.state == Level52TransitionState.COMPLETE
    assert res.character_level == 60
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# Scenario 16: Level 60 with verified pre-swap build (BLOCKED, missed_transition = True)
# ==============================================================================
def test_golden_16_level_60_verified_preswap_build_is_blocked_and_missed() -> None:
    """Level 60 with verified pre-swap build evaluates to BLOCKED, missed_transition = True."""
    res = evaluate_level52_transition(
        character_level=60,
        has_verified_preswap_evidence=True,
    )
    assert res.state == Level52TransitionState.BLOCKED
    assert res.character_level == 60
    assert res.transition_pending is True
    assert res.missed_transition is True


# ==============================================================================
# Scenario 17: Level 60 build differs from snapshot and evidence insufficient (VERIFYING)
# ==============================================================================
def test_golden_17_level_60_differs_lvl52_snapshot_evidence_insufficient_verifying() -> None:
    """Level 60 build differs from snapshot and evidence insufficient evaluates to VERIFYING."""
    completion_rule = GuideRule(
        id="SWAP_LVL_52",
        name="Level 52 Weapon Swap Milestone",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.COMPLETION_EVIDENCE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res = evaluate_level52_transition(
        character_level=60,
        rules=[completion_rule],
        evidence_map={"SWAP_LVL_52": None},  # Insufficient / unobserved
        has_verified_preswap_evidence=False,
    )
    assert res.state == Level52TransitionState.VERIFYING
    assert res.character_level == 60
    assert res.transition_pending is True
    assert res.missed_transition is False


# ==============================================================================
# Scenario 18: Skill weapon-set inference is not used for completion
# ==============================================================================
def test_golden_18_skill_weapon_set_inference_not_used_for_completion() -> None:
    """Skill weapon-set inference is not used for completion: completion relies on USABLE rules."""
    completion_rule = GuideRule(
        id="SWAP_LVL_52",
        name="Level 52 Weapon Swap Milestone",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.COMPLETION_EVIDENCE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )

    # 1. Even when skill weapon-set context in delta is unobserved or DEFAULT_OR_SHARED,
    # completion evidence rule directly proves COMPLETE without needing skill weapon assignments
    delta_with_unassigned_skills = BuildDeltaResult(
        character_id="hero_lvl52",
        character_level=52,
        progression_phase=ProgressionPhase.POST_52_53_68,
        target_stage_name="lvl 53-68",
        target_variant_resolution=TargetVariantResolution(status=VariantResolutionStatus.NOT_APPLICABLE),
        skills=[
            SkillGroupDeltaEntry(
                logical_key=("Flameblast", None),
                primary_gem_id="Flameblast",
                status=DeltaStatus.PRESENT,
                reason=DeltaReason.NONE,
                level_interval=LevelInterval(kind=IntervalKind.RANGE, min_level=1, max_level=100),
            )
        ],
    )

    res1 = evaluate_level52_transition(
        character_level=52,
        current_state=Level52TransitionState.TRANSITIONING,
        delta=delta_with_unassigned_skills,
        rules=[completion_rule],
        evidence_map={"SWAP_LVL_52": True},
    )
    assert res1.state == Level52TransitionState.COMPLETE

    # 2. Fabricated skill weapon sets in delta cannot replace missing completion evidence
    delta_with_assigned_skills = BuildDeltaResult(
        character_id="hero_lvl52",
        character_level=52,
        progression_phase=ProgressionPhase.POST_52_53_68,
        target_stage_name="lvl 53-68",
        target_variant_resolution=TargetVariantResolution(status=VariantResolutionStatus.NOT_APPLICABLE),
        skills=[
            SkillGroupDeltaEntry(
                logical_key=("Flameblast", "SET_1"),
                primary_gem_id="Flameblast",
                status=DeltaStatus.PRESENT,
                reason=DeltaReason.NONE,
                level_interval=LevelInterval(kind=IntervalKind.RANGE, min_level=1, max_level=100),
            )
        ],
    )
    res2 = evaluate_level52_transition(
        character_level=52,
        current_state=Level52TransitionState.TRANSITIONING,
        delta=delta_with_assigned_skills,
        rules=[completion_rule],
        evidence_map={"SWAP_LVL_52": None},  # No completion evidence
    )
    assert res2.state != Level52TransitionState.COMPLETE
    assert res2.state == Level52TransitionState.TRANSITIONING


# ==============================================================================
# Scenario 19: Migrated 2.0 state at level 20 has transition = None, initializes NOT_RELEVANT
# ==============================================================================
def test_golden_19_migrated_2_0_level_20_transition_none_initializes_not_relevant() -> None:
    """Migrated 2.0 state at level 20 has transition = None, first evaluation initializes NOT_RELEVANT."""
    char = CharacterState.create_initial(character_id="migrated_20", character_name="Migrated20")
    char.level = ProvenancedField[int].create(20, source="TEST", verification_state=VerificationState.VERIFIED)
    assert char.transition is None

    res = evaluate_level52_transition(character_state=char)
    assert res.state == Level52TransitionState.NOT_RELEVANT
    assert res.character_level == 20
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# Scenario 20: Migrated 2.0 state at level 52 has transition = None, initializes VERIFYING
# ==============================================================================
def test_golden_20_migrated_2_0_level_52_transition_none_initializes_verifying() -> None:
    """Migrated 2.0 state at level 52 has transition = None, first evaluation initializes VERIFYING."""
    char = CharacterState.create_initial(character_id="migrated_52", character_name="Migrated52")
    char.level = ProvenancedField[int].create(52, source="TEST", verification_state=VerificationState.VERIFIED)
    assert char.transition is None

    res = evaluate_level52_transition(character_state=char)
    assert res.state == Level52TransitionState.VERIFYING
    assert res.character_level == 52
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# Scenario 21: Migrated 2.0 state at level 60 with completion evidence initializes COMPLETE
# ==============================================================================
def test_golden_21_migrated_2_0_level_60_completion_evidence_initializes_complete() -> None:
    """Migrated 2.0 state at level 60 with completion evidence has transition = None, initializes COMPLETE."""
    char = CharacterState.create_initial(character_id="migrated_60", character_name="Migrated60")
    char.level = ProvenancedField[int].create(60, source="TEST", verification_state=VerificationState.VERIFIED)
    assert char.transition is None

    res = evaluate_level52_transition(
        character_state=char,
        has_verified_completion_evidence=True,
    )
    assert res.state == Level52TransitionState.COMPLETE
    assert res.character_level == 60
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# Scenario 22: Restart while VERIFYING preserves state
# ==============================================================================
def test_golden_22_restart_while_verifying_preserves_state(tmp_path: Path) -> None:
    """Restart while VERIFYING preserves state across process boundaries."""
    store = CharacterStateStore(tmp_path)
    char = CharacterState.create_initial(character_id="hero_verifying", character_name="HeroVerifying")
    char.level = ProvenancedField[int].create(52, source="TEST", verification_state=VerificationState.VERIFIED)
    char.transition = Level52TransitionRecord(
        state=Level52TransitionState.VERIFYING,
        requirements={"SWAP_LVL_52": RequirementReadiness.UNKNOWN},
        last_evaluated_at="2026-03-31T12:00:00Z",
        notes="Awaiting gear scan",
    )
    store.save_character(char)

    # Fresh process restart simulation
    fresh_store = CharacterStateStore(tmp_path)
    reloaded = fresh_store.load_character("hero_verifying")
    assert reloaded.transition is not None
    assert reloaded.transition.state == Level52TransitionState.VERIFYING
    assert reloaded.transition.notes == "Awaiting gear scan"

    eval_result = evaluate_level52_transition(character_state=reloaded)
    assert eval_result.state == Level52TransitionState.VERIFYING


# ==============================================================================
# Scenario 23: Restart while BLOCKED preserves state
# ==============================================================================
def test_golden_23_restart_while_blocked_preserves_state(tmp_path: Path) -> None:
    """Restart while BLOCKED preserves state across process boundaries."""
    blocking_rule = GuideRule(
        id="REQUIRED_OFFHAND",
        name="Required Offhand",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    store = CharacterStateStore(tmp_path)
    char = CharacterState.create_initial(character_id="hero_blocked", character_name="HeroBlocked")
    char.level = ProvenancedField[int].create(52, source="TEST", verification_state=VerificationState.VERIFIED)
    char.transition = Level52TransitionRecord(
        state=Level52TransitionState.BLOCKED,
        requirements={"REQUIRED_OFFHAND": RequirementReadiness.UNSATISFIED},
        last_evaluated_at="2026-03-31T12:00:00Z",
        notes="Missing required offhand",
    )
    store.save_character(char)

    # Fresh process restart simulation
    fresh_store = CharacterStateStore(tmp_path)
    reloaded = fresh_store.load_character("hero_blocked")
    assert reloaded.transition is not None
    assert reloaded.transition.state == Level52TransitionState.BLOCKED
    assert reloaded.transition.requirements == {"REQUIRED_OFFHAND": RequirementReadiness.UNSATISFIED}

    eval_result = evaluate_level52_transition(
        character_state=reloaded,
        rules=[blocking_rule],
        evidence_map={"REQUIRED_OFFHAND": False},
    )
    assert eval_result.state == Level52TransitionState.BLOCKED


# ==============================================================================
# Scenario 24: Restart while READY preserves state
# ==============================================================================
def test_golden_24_restart_while_ready_preserves_state(tmp_path: Path) -> None:
    """Restart while READY preserves state across process boundaries."""
    store = CharacterStateStore(tmp_path)
    char = CharacterState.create_initial(character_id="hero_ready", character_name="HeroReady")
    char.level = ProvenancedField[int].create(52, source="TEST", verification_state=VerificationState.VERIFIED)
    char.transition = Level52TransitionRecord(
        state=Level52TransitionState.READY,
        requirements={"SWAP_STAFF": RequirementReadiness.SATISFIED},
        last_evaluated_at="2026-03-31T12:00:00Z",
        notes="Ready for weapon swap",
    )
    store.save_character(char)

    # Fresh process restart simulation
    fresh_store = CharacterStateStore(tmp_path)
    reloaded = fresh_store.load_character("hero_ready")
    assert reloaded.transition is not None
    assert reloaded.transition.state == Level52TransitionState.READY

    eval_result = evaluate_level52_transition(
        character_state=reloaded,
        evidence_map={"SWAP_STAFF": True},
    )
    assert eval_result.state == Level52TransitionState.READY


# ==============================================================================
# Scenario 25: Restart while COMPLETE preserves state
# ==============================================================================
def test_golden_25_restart_while_complete_preserves_state(tmp_path: Path) -> None:
    """Restart while COMPLETE preserves state across process boundaries and level advancement."""
    store = CharacterStateStore(tmp_path)
    char = CharacterState.create_initial(character_id="hero_complete", character_name="HeroComplete")
    char.level = ProvenancedField[int].create(52, source="TEST", verification_state=VerificationState.VERIFIED)
    char.transition = Level52TransitionRecord(
        state=Level52TransitionState.COMPLETE,
        requirements={"SWAP_LVL_52": RequirementReadiness.SATISFIED},
        last_evaluated_at="2026-03-31T12:00:00Z",
        verified_at="2026-03-31T12:00:00Z",
        notes="Transition milestone verified",
    )
    store.save_character(char)

    # Fresh process restart simulation
    fresh_store = CharacterStateStore(tmp_path)
    reloaded = fresh_store.load_character("hero_complete")
    assert reloaded.transition is not None
    assert reloaded.transition.state == Level52TransitionState.COMPLETE
    assert reloaded.transition.verified_at == "2026-03-31T12:00:00Z"

    # Evaluates to COMPLETE even upon advancement to level 60
    reloaded.level = ProvenancedField[int].create(60, source="TEST", verification_state=VerificationState.VERIFIED)
    eval_result = evaluate_level52_transition(character_state=reloaded)
    assert eval_result.state == Level52TransitionState.COMPLETE
    assert eval_result.character_level == 60
    assert eval_result.transition_pending is False
    assert eval_result.missed_transition is False


# ==============================================================================
# Scenario 26: Conflicting source/evidence yields CONFLICTING_EVIDENCE
# ==============================================================================
def test_golden_26_conflicting_source_evidence_yields_conflicting_evidence() -> None:
    """Conflicting source/evidence yields CONFLICTING_EVIDENCE state and safe VERIFYING evaluation."""
    rule = GuideRule(
        id="RULE_CONFLICT",
        name="Conflicting Gear Rule",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )

    # 1. Rule evaluator yields CONFLICTING_EVIDENCE
    rule_res = evaluate_rule(
        rule=rule,
        evidence=RuleEvidence(is_conflicting=True),
        character_level=52,
    )
    assert rule_res.state == RuleEvaluationState.CONFLICTING_EVIDENCE
    assert rule_res.reason == "CONFLICTING_EVIDENCE"

    # 2. Single requirement evaluation yields UNKNOWN readiness with CONFLICTING_EVIDENCE reason
    req_eval = evaluate_single_requirement(
        rule=rule,
        evidence=RuleEvidence(is_conflicting=True),
        character_level=52,
    )
    assert req_eval.readiness == RequirementReadiness.UNKNOWN
    assert req_eval.reason == "CONFLICTING_EVIDENCE"
    assert req_eval.is_active_blocker is False

    # 3. Transition evaluator handles conflicting evidence as VERIFYING (not false BLOCKED)
    res = evaluate_level52_transition(
        character_level=52,
        rules=[rule],
        evidence_map={"RULE_CONFLICT": RuleEvidence(is_conflicting=True)},
    )
    assert res.state == Level52TransitionState.VERIFYING
    assert res.character_level == 52
    assert res.transition_pending is False
    assert res.missed_transition is False
