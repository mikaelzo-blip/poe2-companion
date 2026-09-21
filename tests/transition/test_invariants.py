"""Invariant property tests for Milestone 3 Level-52 Transition.

Explicitly tests and proves all 22 domain invariants:
1.  No invented pre-52 preparation threshold (level < 52 is NOT_RELEVANT unless explicit usable preparation rule exists)
2.  Requirement type does not implicitly determine transition role
3.  Only USABLE BLOCKING_REQUIREMENT rules can directly cause BLOCKED
4.  PENDING_SOURCE_VERIFICATION rules cannot deadlock READY
5.  Only USABLE COMPLETION_EVIDENCE may prove COMPLETE
6.  COMPLETE does not require exact equality to lvl52 snapshot
7.  No skill weapon-set inference is required for COMPLETE
8.  Schema migration does not invent historical transition state (transition = None)
9.  First post-migration evaluation is deterministic
10. transition_pending is not allowed to drift independently from canonical transition state
11. UNKNOWN never becomes FAIL merely due to absence of evidence
12. FUTURE requirement never blocks current transition
13. NOT_APPLICABLE requirement never blocks
14. BLOCKED requires verified applicable failure
15. READY requires all applicable blockers definitively satisfied
16. level > 52 alone never means COMPLETE
17. level > 52 does not erase an incomplete transition
18. Companion installed late can recognize an already-completed transition
19. COMPLETE survives restart and level advancement
20. Future progression requirements do not reopen completed Level-52 transition
21. M3 does not independently recompute M2 eligibility/delta semantics
22. State-machine evaluation is deterministic for identical persistent state and evidence
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
from companion.state.migrations import apply_migrations, migrate_2_0_to_3_0
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
    get_active_blocking_requirements,
    get_applicable_blocking_requirements,
    has_unsatisfied_blocker,
    is_transition_ready,
)
from companion.transition.state import (
    Level52TransitionRecord,
    Level52TransitionResult,
    Level52TransitionState,
)


# ==============================================================================
# Invariant 1: No invented pre-52 preparation threshold
# ==============================================================================
@pytest.mark.parametrize("level", [1, 10, 20, 30, 45, 50, 51])
def test_invariant_01_no_invented_pre52_preparation_threshold(level: int) -> None:
    """Level < 52 is strictly NOT_RELEVANT unless an explicit usable preparation rule exists.

    No arbitrary or invented threshold at level 45, 50, or 51 triggers PREPARING.
    """
    # 1. Without usable preparation rule, all levels evaluate to NOT_RELEVANT
    res_no_prep = evaluate_level52_transition(character_level=level)
    assert res_no_prep.state == Level52TransitionState.NOT_RELEVANT
    assert res_no_prep.character_level == level
    assert res_no_prep.transition_pending is False
    assert res_no_prep.missed_transition is False

    # 2. Preparation requires an explicit USABLE preparation rule
    prep_rule = GuideRule(
        id="EXPLICIT_PREP",
        name="Explicit Preparation Rule",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.PREPARATION,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=45,
        max_level=51,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res_prep = evaluate_level52_transition(
        character_level=level,
        rules=[prep_rule],
        evidence_map={"EXPLICIT_PREP": True},
    )
    if 45 <= level <= 51:
        assert res_prep.state == Level52TransitionState.PREPARING
    else:
        assert res_prep.state == Level52TransitionState.NOT_RELEVANT


# ==============================================================================
# Invariant 2: Requirement type does not implicitly determine transition role
# ==============================================================================
def test_invariant_02_requirement_type_decoupled_from_transition_role() -> None:
    """RequirementType does not implicitly determine transition role.

    All RequirementTypes can be assigned any TransitionRuleRole orthogonally.
    """
    for req_type in RequirementType:
        for role in TransitionRuleRole:
            rule = GuideRule(
                id=f"RULE_{req_type.value}_{role.value}",
                name=f"Rule {req_type.value} {role.value}",
                requirement_type=req_type,
                transition_role=role,
                source_status=SourceVerificationStatus.USABLE,
                min_level=52,
                observable_via=[ObservabilityMethod.GEAR_AUDIT],
            )
            # Evaluated rule must strictly preserve the explicitly assigned transition_role
            req_eval = evaluate_single_requirement(rule=rule, character_level=52, evidence=True)
            assert req_eval.transition_role == role
            assert req_eval.is_satisfied is True


# ==============================================================================
# Invariant 3: Only USABLE BLOCKING_REQUIREMENT rules can directly cause BLOCKED
# ==============================================================================
def test_invariant_03_only_usable_blocking_requirement_rules_cause_blocked() -> None:
    """Only USABLE rules with role BLOCKING_REQUIREMENT can directly cause BLOCKED."""
    roles_and_statuses = [
        (TransitionRuleRole.ADVISORY, SourceVerificationStatus.USABLE),
        (TransitionRuleRole.PREPARATION, SourceVerificationStatus.USABLE),
        (TransitionRuleRole.COMPLETION_EVIDENCE, SourceVerificationStatus.USABLE),
        (TransitionRuleRole.BLOCKING_REQUIREMENT, SourceVerificationStatus.PENDING_SOURCE_VERIFICATION),
        (TransitionRuleRole.BLOCKING_REQUIREMENT, SourceVerificationStatus.UNAVAILABLE),
    ]

    for role, status in roles_and_statuses:
        non_blocking_rule = GuideRule(
            id=f"RULE_{role.value}_{status.value}",
            name="Non-blocking candidate",
            transition_role=role,
            source_status=status,
            requirement_type=RequirementType.EQUIPMENT,
            min_level=52,
            observable_via=[ObservabilityMethod.GEAR_AUDIT],
        )
        res = evaluate_level52_transition(
            character_level=52,
            rules=[non_blocking_rule],
            evidence_map={non_blocking_rule.id: False},
            has_verified_preswap_evidence=False,
        )
        assert res.state != Level52TransitionState.BLOCKED, f"Failed for {role} with {status}"

    # Only USABLE BLOCKING_REQUIREMENT triggers BLOCKED
    usable_blocker = GuideRule(
        id="USABLE_BLOCKER",
        name="Usable Blocker",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res_blocked = evaluate_level52_transition(
        character_level=52,
        rules=[usable_blocker],
        evidence_map={"USABLE_BLOCKER": False},
        has_verified_preswap_evidence=False,
    )
    assert res_blocked.state == Level52TransitionState.BLOCKED


# ==============================================================================
# Invariant 4: PENDING_SOURCE_VERIFICATION rules cannot deadlock READY
# ==============================================================================
def test_invariant_04_pending_source_verification_rules_cannot_deadlock_ready() -> None:
    """PENDING_SOURCE_VERIFICATION rules cannot deadlock or prevent READY when usable blockers pass."""
    usable_blocker = GuideRule(
        id="USABLE_BLOCKER",
        name="Usable Blocker",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    pending_rule = GuideRule(
        id="PENDING_BLOCKER",
        name="Pending Blocker",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.PENDING_SOURCE_VERIFICATION,
        requirement_type=RequirementType.SKILL,
        min_level=52,
        observable_via=[ObservabilityMethod.SKILL_AUDIT],
    )

    for pending_evidence in [False, None, "UNSATISFIED", "UNKNOWN"]:
        res = evaluate_level52_transition(
            character_level=52,
            rules=[usable_blocker, pending_rule],
            evidence_map={
                "USABLE_BLOCKER": True,
                "PENDING_BLOCKER": pending_evidence,
            },
        )
        assert res.state == Level52TransitionState.READY


# ==============================================================================
# Invariant 5: Only USABLE COMPLETION_EVIDENCE may prove COMPLETE
# ==============================================================================
def test_invariant_05_only_usable_completion_evidence_proves_complete() -> None:
    """Only USABLE rules with role COMPLETION_EVIDENCE can prove COMPLETE."""
    # 1. PENDING_SOURCE_VERIFICATION completion rule cannot establish COMPLETE
    pending_comp = GuideRule(
        id="PENDING_COMP",
        name="Pending Completion Rule",
        transition_role=TransitionRuleRole.COMPLETION_EVIDENCE,
        source_status=SourceVerificationStatus.PENDING_SOURCE_VERIFICATION,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res_pending = evaluate_level52_transition(
        character_level=52,
        rules=[pending_comp],
        evidence_map={"PENDING_COMP": True},
    )
    assert res_pending.state != Level52TransitionState.COMPLETE
    assert res_pending.state == Level52TransitionState.VERIFYING

    # 2. USABLE non-completion rule (e.g. BLOCKING_REQUIREMENT) cannot establish COMPLETE
    usable_blocker = GuideRule(
        id="USABLE_BLOCKER",
        name="Usable Blocker",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res_blocker = evaluate_level52_transition(
        character_level=52,
        rules=[usable_blocker],
        evidence_map={"USABLE_BLOCKER": True},
    )
    assert res_blocker.state == Level52TransitionState.READY  # READY, not COMPLETE

    # 3. USABLE COMPLETION_EVIDENCE proves COMPLETE
    usable_comp = GuideRule(
        id="USABLE_COMP",
        name="Usable Completion Rule",
        transition_role=TransitionRuleRole.COMPLETION_EVIDENCE,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res_comp = evaluate_level52_transition(
        character_level=52,
        rules=[usable_comp],
        evidence_map={"USABLE_COMP": True},
    )
    assert res_comp.state == Level52TransitionState.COMPLETE


# ==============================================================================
# Invariant 6: COMPLETE does not require exact equality to lvl52 snapshot
# ==============================================================================
def test_invariant_06_complete_does_not_require_exact_equality_to_lvl52_snapshot() -> None:
    """COMPLETE does not require exact equality to lvl52 snapshot."""
    completion_rule = GuideRule(
        id="SWAP_LVL_52",
        name="Level 52 Weapon Swap Milestone",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.COMPLETION_EVIDENCE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )

    # Character has evolved build with different items and gems at level 60
    delta_evolved = BuildDeltaResult(
        character_id="evolved_hero",
        character_level=60,
        progression_phase=ProgressionPhase.POST_52_53_68,
        target_stage_name="lvl 53-68",
        target_variant_resolution=TargetVariantResolution(status=VariantResolutionStatus.NOT_APPLICABLE),
        equipment=[
            EquipmentDeltaEntry(
                slot_id="BODY_ARMOUR",
                status=DeltaStatus.MISSING,
                reason=DeltaReason.NONE,
            )
        ],
    )

    res = evaluate_level52_transition(
        character_level=60,
        delta=delta_evolved,
        rules=[completion_rule],
        evidence_map={"SWAP_LVL_52": True},
    )
    assert res.state == Level52TransitionState.COMPLETE
    assert res.character_level == 60
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# Invariant 7: No skill weapon-set inference is required for COMPLETE
# ==============================================================================
def test_invariant_07_no_skill_weapon_set_inference_required_for_complete() -> None:
    """No skill weapon-set inference is required or performed for COMPLETE."""
    completion_rule = GuideRule(
        id="SWAP_LVL_52",
        name="Level 52 Weapon Swap Milestone",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.COMPLETION_EVIDENCE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )

    # Completely unassigned weapon-set context on skills
    delta = BuildDeltaResult(
        character_id="hero_no_weapon_set",
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
            )
        ],
    )

    res = evaluate_level52_transition(
        character_level=52,
        delta=delta,
        rules=[completion_rule],
        evidence_map={"SWAP_LVL_52": True},
    )
    assert res.state == Level52TransitionState.COMPLETE


# ==============================================================================
# Invariant 8: Schema migration does not invent historical transition state
# ==============================================================================
@pytest.mark.parametrize("level", [1, 20, 51, 52, 53, 60, 85, 100])
def test_invariant_08_schema_migration_does_not_invent_historical_transition_state(level: int) -> None:
    """Schema migration leaves transition = None without inferring historical transition state."""
    v2_data = {
        "schema_version": "2.0",
        "character_id": f"char_{level}",
        "character_name": f"Hero{level}",
        "level": {
            "value": level,
            "source": "TEST",
            "verification_state": VerificationState.VERIFIED.value,
        },
    }
    migrated = migrate_2_0_to_3_0(dict(v2_data))
    assert migrated["schema_version"] == "3.0"
    assert migrated["transition"] is None

    full_migrated = apply_migrations(v2_data)
    assert full_migrated["schema_version"] == "3.0"
    assert full_migrated["transition"] is None

    char = CharacterState.model_validate(full_migrated)
    assert char.transition is None


# ==============================================================================
# Invariant 9: First post-migration evaluation is deterministic
# ==============================================================================
@pytest.mark.parametrize("level", [20, 52, 60])
def test_invariant_09_first_post_migration_evaluation_deterministic(level: int) -> None:
    """First post-migration evaluation produces deterministic results across multiple evaluations."""
    char = CharacterState.create_initial(character_id=f"migrated_{level}", character_name=f"Hero{level}")
    char.level = ProvenancedField[int].create(level, source="TEST", verification_state=VerificationState.VERIFIED)
    assert char.transition is None

    res1 = evaluate_level52_transition(character_state=char)
    res2 = evaluate_level52_transition(character_state=char)
    assert res1 == res2
    assert res1.character_level == level


# ==============================================================================
# Invariant 10: transition_pending cannot drift from canonical transition state
# ==============================================================================
def test_invariant_10_transition_pending_cannot_drift_from_canonical_state() -> None:
    """transition_pending is strictly derived as: level > 52 and state != COMPLETE."""
    levels = [1, 20, 51, 52, 53, 58, 60, 85, 100]
    states = list(Level52TransitionState)

    for lvl in levels:
        for st in states:
            result = Level52TransitionResult(state=st, character_level=lvl)
            expected_pending = (lvl > 52 and st != Level52TransitionState.COMPLETE)
            assert result.transition_pending is expected_pending

            # Verify immutability: transition_pending cannot be overwritten
            with pytest.raises(Exception):
                result.transition_pending = not expected_pending  # type: ignore[misc]


# ==============================================================================
# Invariant 11: UNKNOWN never becomes FAIL merely due to absence of evidence
# ==============================================================================
def test_invariant_11_unknown_never_becomes_fail_merely_due_to_absence_of_evidence() -> None:
    """Absence of evidence strictly produces UNKNOWN / VERIFYING, never FAIL / BLOCKED."""
    rule = GuideRule(
        id="TEST_BLOCKER",
        name="Test Blocker",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )

    unobserved_cases = [None, RuleEvidence(is_observed=False), "UNKNOWN", "UNOBSERVED", "NO_EVIDENCE"]
    for ev in unobserved_cases:
        # Rule evaluation
        rule_res = evaluate_rule(rule=rule, evidence=ev, character_level=52)
        assert rule_res.state == RuleEvaluationState.UNKNOWN
        assert rule_res.state != RuleEvaluationState.FAIL

        # Requirement evaluation
        req_eval = evaluate_single_requirement(rule=rule, evidence=ev, character_level=52)
        assert req_eval.readiness == RequirementReadiness.UNKNOWN
        assert req_eval.readiness != RequirementReadiness.UNSATISFIED
        assert req_eval.is_active_blocker is False

        # Transition evaluation
        trans_res = evaluate_level52_transition(
            character_level=52,
            rules=[rule],
            evidence_map={"TEST_BLOCKER": ev},
            has_verified_preswap_evidence=False,
        )
        assert trans_res.state == Level52TransitionState.VERIFYING
        assert trans_res.state != Level52TransitionState.BLOCKED


# ==============================================================================
# Invariant 12: FUTURE requirement never blocks current transition
# ==============================================================================
def test_invariant_12_future_requirement_never_blocks_current_transition() -> None:
    """Requirements with FUTURE eligibility never block transition readiness."""
    future_rule = GuideRule(
        id="FUTURE_GEM",
        name="Future Level 58 Gem",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.SKILL,
        min_level=58,
        max_level=100,
        observable_via=[ObservabilityMethod.SKILL_AUDIT],
    )
    req_eval = evaluate_single_requirement(
        rule=future_rule,
        evidence=False,  # Unsatisfied / missing
        character_level=52,
    )
    assert req_eval.eligibility == EligibilityState.FUTURE
    assert req_eval.readiness == RequirementReadiness.UNKNOWN
    assert req_eval.is_applicable_blocker is False
    assert req_eval.is_active_blocker is False


# ==============================================================================
# Invariant 13: NOT_APPLICABLE requirement never blocks
# ==============================================================================
def test_invariant_13_not_applicable_requirement_never_blocks() -> None:
    """Requirements outside level boundaries (NOT_APPLICABLE) never block transition."""
    expired_rule = GuideRule(
        id="EARLY_LEVELING_GEAR",
        name="Early Leveling Gear",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=1,
        max_level=32,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    req_eval = evaluate_single_requirement(
        rule=expired_rule,
        evidence=False,
        character_level=52,
    )
    assert req_eval.eligibility == EligibilityState.EXPIRED
    assert req_eval.is_applicable_blocker is False
    assert req_eval.is_active_blocker is False


# ==============================================================================
# Invariant 14: BLOCKED requires verified applicable failure
# ==============================================================================
def test_invariant_14_blocked_requires_verified_applicable_failure() -> None:
    """BLOCKED strictly requires a verified failed usable blocker or verified pre-swap evidence."""
    # When evidence is unobserved / partial / stale, state is VERIFYING, never BLOCKED
    res_uncertain = evaluate_level52_transition(
        character_level=52,
        evidence_map={},
        has_verified_preswap_evidence=False,
    )
    assert res_uncertain.state != Level52TransitionState.BLOCKED
    assert res_uncertain.state == Level52TransitionState.VERIFYING

    # Only verified failure causes BLOCKED
    blocker = GuideRule(
        id="USABLE_BLOCKER",
        name="Usable Blocker",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res_failed = evaluate_level52_transition(
        character_level=52,
        rules=[blocker],
        evidence_map={"USABLE_BLOCKER": False},
    )
    assert res_failed.state == Level52TransitionState.BLOCKED


# ==============================================================================
# Invariant 15: READY requires all applicable blockers definitively satisfied
# ==============================================================================
def test_invariant_15_ready_requires_all_applicable_blockers_definitively_satisfied() -> None:
    """READY requires every applicable usable blocker to be RequirementReadiness.SATISFIED."""
    blocker_1 = GuideRule(
        id="BLOCKER_1",
        name="Blocker 1",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    blocker_2 = GuideRule(
        id="BLOCKER_2",
        name="Blocker 2",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )

    # 1. One SATISFIED, one UNKNOWN -> VERIFYING (not READY)
    res1 = evaluate_level52_transition(
        character_level=52,
        rules=[blocker_1, blocker_2],
        evidence_map={"BLOCKER_1": True, "BLOCKER_2": None},
    )
    assert res1.state == Level52TransitionState.VERIFYING

    # 2. Both SATISFIED -> READY
    res2 = evaluate_level52_transition(
        character_level=52,
        rules=[blocker_1, blocker_2],
        evidence_map={"BLOCKER_1": True, "BLOCKER_2": True},
    )
    assert res2.state == Level52TransitionState.READY


# ==============================================================================
# Invariant 16: level > 52 alone never means COMPLETE
# ==============================================================================
@pytest.mark.parametrize("level", [53, 58, 60, 70, 85, 100])
def test_invariant_16_level_greater_than_52_alone_never_means_complete(level: int) -> None:
    """Character level > 52 alone never evaluates to COMPLETE without verified completion evidence."""
    res = evaluate_level52_transition(
        character_level=level,
        evidence_map={},
        has_verified_preswap_evidence=False,
    )
    assert res.state != Level52TransitionState.COMPLETE
    assert res.state == Level52TransitionState.VERIFYING
    assert res.transition_pending is True


# ==============================================================================
# Invariant 17: level > 52 does not erase an incomplete transition
# ==============================================================================
@pytest.mark.parametrize("level", [53, 58, 60, 85])
def test_invariant_17_level_greater_than_52_does_not_erase_incomplete_transition(level: int) -> None:
    """Advancing past level 52 without completing the transition preserves transition_pending = True."""
    res = evaluate_level52_transition(
        character_level=level,
        has_verified_preswap_evidence=False,
    )
    assert res.transition_pending is True
    assert res.state in (Level52TransitionState.VERIFYING, Level52TransitionState.BLOCKED)


# ==============================================================================
# Invariant 18: Companion installed late can recognize an already-completed transition
# ==============================================================================
@pytest.mark.parametrize("level", [52, 55, 60, 85, 100])
def test_invariant_18_late_install_recognizes_already_completed_transition(level: int) -> None:
    """Companion installed late at level >= 52 recognizes COMPLETE with verified completion evidence."""
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
        character_level=level,
        rules=[completion_rule],
        evidence_map={"SWAP_LVL_52": True},
        has_verified_preswap_evidence=False,
    )
    assert res.state == Level52TransitionState.COMPLETE
    assert res.character_level == level
    assert res.transition_pending is False
    assert res.missed_transition is False


# ==============================================================================
# Invariant 19: COMPLETE survives restart and level advancement
# ==============================================================================
def test_invariant_19_complete_survives_restart_and_level_advancement(tmp_path: Path) -> None:
    """COMPLETE survives process restart and subsequent level advancements up to 100."""
    store = CharacterStateStore(tmp_path)
    char = CharacterState.create_initial(character_id="hero_complete_inv", character_name="CompleteHero")
    char.level = ProvenancedField[int].create(52, source="TEST", verification_state=VerificationState.VERIFIED)
    char.transition = Level52TransitionRecord(
        state=Level52TransitionState.COMPLETE,
        verified_at="2026-03-31T12:00:00Z",
    )
    store.save_character(char)

    # Process restart
    fresh_store = CharacterStateStore(tmp_path)
    reloaded = fresh_store.load_character("hero_complete_inv")
    assert reloaded.transition is not None
    assert reloaded.transition.state == Level52TransitionState.COMPLETE

    for adv_level in [53, 58, 68, 85, 100]:
        reloaded.level = ProvenancedField[int].create(adv_level, source="TEST", verification_state=VerificationState.VERIFIED)
        res = evaluate_level52_transition(character_state=reloaded)
        assert res.state == Level52TransitionState.COMPLETE
        assert res.character_level == adv_level
        assert res.transition_pending is False
        assert res.missed_transition is False


# ==============================================================================
# Invariant 20: Future progression requirements do not reopen completed transition
# ==============================================================================
def test_invariant_20_future_progression_requirements_do_not_reopen_completed_transition() -> None:
    """Future progression requirements becoming active/failing do not reopen a completed transition."""
    prior_state = Level52TransitionState.COMPLETE
    cod_rule = GuideRule(
        id="GEM_CAST_ON_DODGE",
        name="Cast on Dodge",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.SKILL,
        min_level=58,
        observable_via=[ObservabilityMethod.SKILL_AUDIT],
    )
    res = evaluate_level52_transition(
        character_level=58,
        current_state=prior_state,
        rules=[cod_rule],
        evidence_map={"GEM_CAST_ON_DODGE": False},  # Active and failing
    )
    assert res.state == Level52TransitionState.COMPLETE
    assert res.transition_pending is False


# ==============================================================================
# Invariant 21: M3 does not independently recompute M2 eligibility/delta semantics
# ==============================================================================
def test_invariant_21_m3_does_not_independently_recompute_m2_semantics() -> None:
    """M3 transition requirement evaluator directly consumes and preserves M2 delta semantics."""
    rule = GuideRule(
        id="RULE_SKILL",
        name="Skill Rule",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.SKILL,
        min_level=52,
        observable_via=[ObservabilityMethod.SKILL_AUDIT],
    )

    # 1. DeltaStatus.FUTURE maps directly to EligibilityState.FUTURE and UNKNOWN readiness
    m2_future_entry = SkillGroupDeltaEntry(
        logical_key=("GemA", None),
        primary_gem_id="GemA",
        status=DeltaStatus.FUTURE,
        reason=DeltaReason.INELIGIBLE_LEVEL,
        level_interval=LevelInterval(kind=IntervalKind.RANGE, min_level=58, max_level=100),
    )
    eval_future = evaluate_single_requirement(rule=rule, evidence=m2_future_entry, character_level=52)
    assert eval_future.eligibility == EligibilityState.FUTURE
    assert eval_future.readiness == RequirementReadiness.UNKNOWN

    # 2. DeltaReason.OBSERVATION_COVERAGE_UNKNOWN maps directly to UNKNOWN readiness with preserved reason
    m2_unobserved_entry = EquipmentDeltaEntry(
        slot_id="RING_1",
        status=DeltaStatus.UNKNOWN,
        reason=DeltaReason.OBSERVATION_COVERAGE_UNKNOWN,
    )
    eval_unobserved = evaluate_single_requirement(rule=rule, evidence=m2_unobserved_entry, character_level=52)
    assert eval_unobserved.readiness == RequirementReadiness.UNKNOWN
    assert eval_unobserved.details.get("delta_reason") == DeltaReason.OBSERVATION_COVERAGE_UNKNOWN.value


# ==============================================================================
# Invariant 22: State-machine evaluation is deterministic for identical inputs
# ==============================================================================
def test_invariant_22_state_machine_evaluation_deterministic_for_identical_inputs() -> None:
    """State-machine evaluation is strictly deterministic for identical persistent state and evidence."""
    rule = GuideRule(
        id="USABLE_BLOCKER",
        name="Usable Blocker",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )

    for _ in range(5):
        res_a = evaluate_level52_transition(
            character_level=52,
            rules=[rule],
            evidence_map={"USABLE_BLOCKER": True},
            evaluated_at="2026-03-31T12:00:00Z",
        )
        res_b = evaluate_level52_transition(
            character_level=52,
            rules=[rule],
            evidence_map={"USABLE_BLOCKER": True},
            evaluated_at="2026-03-31T12:00:00Z",
        )
        assert res_a == res_b
