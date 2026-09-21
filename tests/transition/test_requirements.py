"""Unit tests for tri-state requirement evaluation and future requirement isolation.

Tests compliance with Milestone 3 Tasks 3.1, 3.2, 3.3.
"""

from __future__ import annotations

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
from companion.rules.evaluator import RuleEvidence
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
from companion.sources.interval import LevelInterval
from companion.sources.models_normalized import WeaponSetContext
from companion.state.provenance import ProvenancedField, VerificationState
from companion.state.schema import CharacterState
from companion.transition.requirements import (
    RequirementEvaluation,
    RequirementReadiness,
    evaluate_requirements,
    evaluate_single_requirement,
    get_active_blocking_requirements,
    get_applicable_blocking_requirements,
    has_unknown_blocker,
    has_unsatisfied_blocker,
    is_transition_ready,
)


def test_requirement_readiness_enum_values() -> None:
    """Verify RequirementReadiness has exactly SATISFIED, UNSATISFIED, UNKNOWN."""
    assert len(RequirementReadiness) == 3
    assert RequirementReadiness.SATISFIED == "SATISFIED"
    assert RequirementReadiness.UNSATISFIED == "UNSATISFIED"
    assert RequirementReadiness.UNKNOWN == "UNKNOWN"


def test_requirement_evaluation_model_fields_and_properties() -> None:
    """Verify RequirementEvaluation fields, immutability, and helper properties."""
    evaluation = RequirementEvaluation(
        rule_id="RULE_01",
        rule_name="Test Rule",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        readiness=RequirementReadiness.SATISFIED,
        eligibility=EligibilityState.ACTIVE,
        reason=None,
        details={"note": "ok"},
    )
    assert evaluation.rule_id == "RULE_01"
    assert evaluation.rule_name == "Test Rule"
    assert evaluation.transition_role == TransitionRuleRole.BLOCKING_REQUIREMENT
    assert evaluation.source_status == SourceVerificationStatus.USABLE
    assert evaluation.readiness == RequirementReadiness.SATISFIED
    assert evaluation.eligibility == EligibilityState.ACTIVE
    assert evaluation.reason is None
    assert evaluation.details == {"note": "ok"}

    assert evaluation.is_satisfied is True
    assert evaluation.is_unsatisfied is False
    assert evaluation.is_unknown is False
    assert evaluation.is_active_blocker is False
    assert evaluation.is_applicable_blocker is True


def test_evaluate_single_requirement_satisfied() -> None:
    """Verify fresh verified condition met under USABLE rule evaluates to SATISFIED."""
    rule = GuideRule(
        id="REQ_GEAR",
        name="Equip Staff",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res = evaluate_single_requirement(rule, evidence=True, character_level=52)
    assert res.readiness == RequirementReadiness.SATISFIED
    assert res.is_satisfied is True
    assert res.is_unsatisfied is False
    assert res.is_unknown is False
    assert res.is_active_blocker is False
    assert res.reason is None
    assert res.eligibility == EligibilityState.ACTIVE


def test_evaluate_single_requirement_unsatisfied() -> None:
    """Verify fresh verified condition failed under USABLE rule evaluates to UNSATISFIED."""
    rule = GuideRule(
        id="REQ_GEAR",
        name="Equip Staff",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res = evaluate_single_requirement(rule, evidence=False, character_level=52)
    assert res.readiness == RequirementReadiness.UNSATISFIED
    assert res.is_satisfied is False
    assert res.is_unsatisfied is True
    assert res.is_unknown is False
    assert res.is_active_blocker is True
    assert res.reason == "CONDITION_UNSATISFIED"
    assert res.eligibility == EligibilityState.ACTIVE


def test_unknown_is_neither_satisfied_nor_active_blocker() -> None:
    """Verify UNKNOWN readiness is neither satisfied nor an active blocker."""
    rule = GuideRule(
        id="REQ_UNKNOWN",
        name="Unknown Requirement",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res = evaluate_single_requirement(rule, evidence=None, character_level=52)
    assert res.readiness == RequirementReadiness.UNKNOWN
    assert res.is_satisfied is False
    assert res.is_unsatisfied is False
    assert res.is_unknown is True
    assert res.is_active_blocker is False

    evals = [res]
    assert get_active_blocking_requirements(evals) == []
    assert has_unsatisfied_blocker(evals) is False
    assert has_unknown_blocker(evals) is True
    assert is_transition_ready(evals) is False  # Cannot be READY while blocker is UNKNOWN


def test_stale_evidence_maps_to_unknown_readiness() -> None:
    """Verify stale observation strictly maps to UNKNOWN readiness with STALE reason."""
    rule = GuideRule(
        id="REQ_STALE",
        name="Stale Requirement",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res = evaluate_single_requirement(
        rule,
        evidence=RuleEvidence(satisfied=True, is_stale=True),
        character_level=52,
    )
    assert res.readiness == RequirementReadiness.UNKNOWN
    assert res.is_active_blocker is False
    assert "STALE" in (res.reason or "")
    assert res.details.get("rule_evaluation_state") == RuleEvaluationState.STALE.value


def test_partial_and_unobserved_evidence_maps_to_unknown_readiness() -> None:
    """Verify partial and unobserved observations strictly map to UNKNOWN readiness."""
    rule = GuideRule(
        id="REQ_PARTIAL",
        name="Partial Observation Rule",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    # Unobserved
    res_unobs = evaluate_single_requirement(
        rule,
        evidence=RuleEvidence(is_observed=False),
        character_level=52,
    )
    assert res_unobs.readiness == RequirementReadiness.UNKNOWN
    assert res_unobs.is_active_blocker is False
    assert "UNOBSERVED" in (res_unobs.reason or "") or "NO_EVIDENCE" in (res_unobs.reason or "")

    # Partial observation via M2 EquipmentDeltaEntry with PARTIAL_PLAYER_OBSERVATION
    entry_partial = EquipmentDeltaEntry(
        slot_id="MainHand",
        status=DeltaStatus.UNKNOWN,
        reason=DeltaReason.PARTIAL_PLAYER_OBSERVATION,
    )
    res_partial = evaluate_single_requirement(rule, evidence=entry_partial, character_level=52)
    assert res_partial.readiness == RequirementReadiness.UNKNOWN
    assert res_partial.is_active_blocker is False
    assert res_partial.details.get("delta_reason") == DeltaReason.PARTIAL_PLAYER_OBSERVATION.value


def test_conflicting_evidence_maps_to_unknown_readiness() -> None:
    """Verify contradictory evidence strictly maps to UNKNOWN readiness."""
    rule = GuideRule(
        id="REQ_CONFLICT",
        name="Conflicting Requirement",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    res = evaluate_single_requirement(
        rule,
        evidence=RuleEvidence(is_conflicting=True),
        character_level=52,
    )
    assert res.readiness == RequirementReadiness.UNKNOWN
    assert res.is_active_blocker is False
    assert "CONFLICTING" in (res.reason or "")
    assert res.details.get("rule_evaluation_state") == RuleEvaluationState.CONFLICTING_EVIDENCE.value


def test_m2_delta_consumption_equipment_skills_passives() -> None:
    """Verify evaluate_requirements consumes M2 deltas across equipment, skills, and passives."""
    rule_gear = GuideRule(
        id="RULE_GEAR",
        name="MainHand Weapon",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        expected={"slot_id": "MainHand"},
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    rule_skill = GuideRule(
        id="RULE_SKILL",
        name="Primary Flameblast",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.SKILL,
        min_level=52,
        expected={"gem_id": "Flameblast"},
        observable_via=[ObservabilityMethod.SKILL_AUDIT],
    )
    rule_passive = GuideRule(
        id="RULE_PASSIVE",
        name="Avatar of Fire",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.PASSIVE,
        min_level=52,
        expected={"passive_id": "passive_avatar_of_fire"},
        observable_via=[ObservabilityMethod.PASSIVE_AUDIT],
    )

    delta = BuildDeltaResult(
        character_id="hero1",
        character_level=52,
        progression_phase=ProgressionPhase.POST_52_53_68,
        target_variant_resolution=TargetVariantResolution(
            status=VariantResolutionStatus.NOT_APPLICABLE,
        ),
        target_stage_name="lvl 52 Swap",
        equipment=[
            EquipmentDeltaEntry(slot_id="MainHand", status=DeltaStatus.PRESENT),
        ],
        skills=[
            SkillGroupDeltaEntry(
                logical_key=("Flameblast", None),
                primary_gem_id="Flameblast",
                status=DeltaStatus.PRESENT,
            ),
        ],
        passives=[
            PassiveDeltaEntry(
                key=("passive_avatar_of_fire", WeaponSetContext.DEFAULT_OR_SHARED),
                passive_id="passive_avatar_of_fire",
                weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
                status=DeltaStatus.MISSING,
            ),
        ],
    )

    evaluations = evaluate_requirements(
        rules=[rule_gear, rule_skill, rule_passive],
        delta=delta,
        character_level=52,
    )

    assert len(evaluations) == 3
    eval_map = {e.rule_id: e for e in evaluations}

    assert eval_map["RULE_GEAR"].readiness == RequirementReadiness.SATISFIED
    assert eval_map["RULE_SKILL"].readiness == RequirementReadiness.SATISFIED
    assert eval_map["RULE_PASSIVE"].readiness == RequirementReadiness.UNSATISFIED
    assert eval_map["RULE_PASSIVE"].is_active_blocker is True

    # Passive is an active blocker, so not ready and has unsatisfied blocker
    active_blockers = get_active_blocking_requirements(evaluations)
    assert len(active_blockers) == 1
    assert active_blockers[0].rule_id == "RULE_PASSIVE"
    assert has_unsatisfied_blocker(evaluations) is True
    assert is_transition_ready(evaluations) is False


def test_future_requirement_isolation_cast_on_dodge_at_level_52() -> None:
    """Verify Cast on Dodge [58, 100] at level 52 evaluates to FUTURE and never blocks readiness."""
    cod_rule = GuideRule(
        id="GEM_CAST_ON_DODGE",
        name="Cast on Dodge Meta-Gem Milestone",
        provenance=RuleSourceType.BLUEPRINT_V2,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.SKILL,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        min_level=58,
        max_level=100,
        observable_via=[ObservabilityMethod.SKILL_AUDIT],
    )
    gear_rule = GuideRule(
        id="SWAP_STAFF",
        name="Equip Staff",
        provenance=RuleSourceType.BLUEPRINT_V2,
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.EQUIPMENT,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )

    # 1. At level 52 with Cast on Dodge missing from player audit, but staff equipped (SATISFIED)
    cod_delta_entry = SkillGroupDeltaEntry(
        logical_key=("CastOnDodge", None),
        primary_gem_id="CastOnDodge",
        status=DeltaStatus.FUTURE,
        reason=DeltaReason.INELIGIBLE_LEVEL,
        level_interval=LevelInterval(kind="RANGE", min_level=58, max_level=100),
    )

    evaluations = evaluate_requirements(
        rules=[gear_rule, cod_rule],
        evidence_map={
            "SWAP_STAFF": True,
            "GEM_CAST_ON_DODGE": cod_delta_entry,
        },
        character_level=52,
    )

    eval_map = {e.rule_id: e for e in evaluations}

    # Gear rule is satisfied
    assert eval_map["SWAP_STAFF"].readiness == RequirementReadiness.SATISFIED
    assert eval_map["SWAP_STAFF"].is_applicable_blocker is True

    # Cast on Dodge evaluates to FUTURE eligibility
    cod_eval = eval_map["GEM_CAST_ON_DODGE"]
    assert cod_eval.eligibility == EligibilityState.FUTURE
    assert cod_eval.readiness == RequirementReadiness.UNKNOWN
    assert cod_eval.is_active_blocker is False
    assert cod_eval.is_applicable_blocker is False

    # Blockers calculation strictly excludes Cast on Dodge
    active_blockers = get_active_blocking_requirements(evaluations)
    assert active_blockers == []
    assert has_unsatisfied_blocker(evaluations) is False

    # Ready evaluation: gear is satisfied, Cast on Dodge is FUTURE -> TRANSITION IS READY
    assert is_transition_ready(evaluations) is True


def test_cast_on_dodge_becomes_active_at_level_58() -> None:
    """Verify Cast on Dodge [58, 100] becomes ACTIVE at level 58 and gates blocking if unsatisfied."""
    cod_rule = GuideRule(
        id="GEM_CAST_ON_DODGE",
        name="Cast on Dodge Meta-Gem Milestone",
        source_status=SourceVerificationStatus.USABLE,
        requirement_type=RequirementType.SKILL,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        min_level=58,
        max_level=100,
        observable_via=[ObservabilityMethod.SKILL_AUDIT],
    )

    # At level 58, Cast on Dodge is missing from player audit (DeltaStatus.MISSING)
    cod_delta_entry = SkillGroupDeltaEntry(
        logical_key=("CastOnDodge", None),
        primary_gem_id="CastOnDodge",
        status=DeltaStatus.MISSING,
        reason=DeltaReason.NONE,
        level_interval=LevelInterval(kind="RANGE", min_level=58, max_level=100),
    )

    evaluations = evaluate_requirements(
        rules=[cod_rule],
        evidence_map={"GEM_CAST_ON_DODGE": cod_delta_entry},
        character_level=58,
    )

    cod_eval = evaluations[0]
    assert cod_eval.eligibility == EligibilityState.ACTIVE
    assert cod_eval.readiness == RequirementReadiness.UNSATISFIED
    assert cod_eval.is_active_blocker is True
    assert cod_eval.is_applicable_blocker is True

    assert has_unsatisfied_blocker(evaluations) is True
    assert is_transition_ready(evaluations) is False


def test_only_usable_blocking_requirement_rules_can_be_active_blockers() -> None:
    """Verify ADVISORY, PREPARATION, COMPLETION_EVIDENCE, and non-USABLE rules never block."""
    rules = [
        GuideRule(
            id="RULE_ADVISORY",
            name="Advisory Rule",
            source_status=SourceVerificationStatus.USABLE,
            transition_role=TransitionRuleRole.ADVISORY,
            min_level=52,
            observable_via=[ObservabilityMethod.API],
        ),
        GuideRule(
            id="RULE_PREP",
            name="Preparation Rule",
            source_status=SourceVerificationStatus.USABLE,
            transition_role=TransitionRuleRole.PREPARATION,
            min_level=33,
            max_level=51,
            observable_via=[ObservabilityMethod.API],
        ),
        GuideRule(
            id="RULE_COMPLETION",
            name="Completion Evidence Rule",
            source_status=SourceVerificationStatus.USABLE,
            transition_role=TransitionRuleRole.COMPLETION_EVIDENCE,
            min_level=52,
            observable_via=[ObservabilityMethod.API],
        ),
        GuideRule(
            id="RULE_PENDING",
            name="Pending Source Rule",
            source_status=SourceVerificationStatus.PENDING_SOURCE_VERIFICATION,
            transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
            min_level=52,
            observable_via=[ObservabilityMethod.API],
        ),
        GuideRule(
            id="RULE_UNAVAIL",
            name="Unavailable Rule",
            source_status=SourceVerificationStatus.UNAVAILABLE,
            transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
            min_level=52,
            observable_via=[ObservabilityMethod.API],
        ),
    ]

    # All conditions fail
    evidence_map = {
        "RULE_ADVISORY": False,
        "RULE_PREP": False,
        "RULE_COMPLETION": False,
        "RULE_PENDING": False,
        "RULE_UNAVAIL": False,
    }

    evaluations = evaluate_requirements(
        rules=rules,
        evidence_map=evidence_map,
        character_level=52,
    )

    # None of them can be active blockers
    active_blockers = get_active_blocking_requirements(evaluations)
    assert active_blockers == []
    assert has_unsatisfied_blocker(evaluations) is False
    assert is_transition_ready(evaluations) is True  # No applicable usable blockers


def test_pending_source_verification_rules_cannot_deadlock_ready() -> None:
    """Verify PENDING_SOURCE_VERIFICATION rules evaluate to UNKNOWN but never deadlock READY."""
    usable_blocker = GuideRule(
        id="USABLE_BLOCKER",
        name="Staff Equipped",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    pending_blocker = GuideRule(
        id="PENDING_BLOCKER",
        name="Unverified Guide Rule",
        source_status=SourceVerificationStatus.PENDING_SOURCE_VERIFICATION,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )

    evaluations = evaluate_requirements(
        rules=[usable_blocker, pending_blocker],
        evidence_map={
            "USABLE_BLOCKER": True,      # Satisfied
            "PENDING_BLOCKER": False,    # Even if failing or unobserved
        },
        character_level=52,
    )

    eval_map = {e.rule_id: e for e in evaluations}
    assert eval_map["USABLE_BLOCKER"].readiness == RequirementReadiness.SATISFIED
    assert eval_map["PENDING_BLOCKER"].readiness == RequirementReadiness.UNKNOWN
    assert eval_map["PENDING_BLOCKER"].reason == "PENDING_SOURCE_VERIFICATION"

    # Pending rule does not deadlock READY
    assert is_transition_ready(evaluations) is True
    assert has_unsatisfied_blocker(evaluations) is False


def test_evaluate_frozen_guide_rules_at_level_52() -> None:
    """Verify evaluate_requirements integrates cleanly with default frozen guide_rules.yaml."""
    frozen_rules = load_guide_rules()
    assert len(frozen_rules) >= 4

    evaluations = evaluate_requirements(
        rules=frozen_rules,
        character_level=52,
    )

    eval_map = {e.rule_id: e for e in evaluations}

    # SWAP_LVL_52 is COMPLETION_EVIDENCE, not a blocker
    assert eval_map["SWAP_LVL_52"].transition_role == TransitionRuleRole.COMPLETION_EVIDENCE
    assert eval_map["SWAP_LVL_52"].is_active_blocker is False

    # GEM_CAST_ON_DODGE is FUTURE at level 52
    assert eval_map["GEM_CAST_ON_DODGE"].eligibility == EligibilityState.FUTURE
    assert eval_map["GEM_CAST_ON_DODGE"].is_active_blocker is False

    # FUBGUN_WRITTEN_GUIDE_GEAR_PRIORITIES is PENDING and min=33, max=51 (so not applicable at 52)
    assert eval_map["FUBGUN_WRITTEN_GUIDE_GEAR_PRIORITIES"].source_status == SourceVerificationStatus.PENDING_SOURCE_VERIFICATION
    assert eval_map["FUBGUN_WRITTEN_GUIDE_GEAR_PRIORITIES"].is_active_blocker is False

    # FUBGUN_WRITTEN_GUIDE_FLASK_SETUP is ADVISORY and PENDING
    assert eval_map["FUBGUN_WRITTEN_GUIDE_FLASK_SETUP"].transition_role == TransitionRuleRole.ADVISORY
    assert eval_map["FUBGUN_WRITTEN_GUIDE_FLASK_SETUP"].is_active_blocker is False

    # At level 52 with no other usable blockers, no active blockers exist
    assert get_active_blocking_requirements(evaluations) == []
    assert has_unsatisfied_blocker(evaluations) is False


def test_delta_conflicts_propagate_to_conflicting_readiness() -> None:
    """Verify conflicts in BuildDeltaResult map to UNKNOWN readiness with CONFLICTING reason."""
    rule = GuideRule(
        id="RULE_CONFLICTING",
        name="Conflicted Passive",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.PASSIVE,
        min_level=52,
        observable_via=[ObservabilityMethod.PASSIVE_AUDIT],
    )

    delta = BuildDeltaResult(
        character_id="hero1",
        character_level=52,
        progression_phase=ProgressionPhase.POST_52_53_68,
        target_variant_resolution=TargetVariantResolution(
            status=VariantResolutionStatus.NOT_APPLICABLE,
        ),
        target_stage_name="lvl 52 Swap",
        conflicts=[
            ConflictRecord(
                field_name="RULE_CONFLICTING",
                details="Contradictory weapon set contexts",
            )
        ],
    )

    evaluations = evaluate_requirements(rules=[rule], delta=delta, character_level=52)
    ev = evaluations[0]
    assert ev.readiness == RequirementReadiness.UNKNOWN
    assert "CONFLICTING" in (ev.reason or "")
    assert ev.is_active_blocker is False
    assert is_transition_ready(evaluations) is False


def test_evaluate_requirements_extracts_level_from_character_state() -> None:
    """Verify evaluate_requirements extracts level and handles character_state."""
    rule = GuideRule(
        id="REQ_LVL52",
        name="Staff Milestone",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.API],
    )

    char_50 = CharacterState(
        character_id="hero1",
        character_name="Merc",
        level=ProvenancedField[int].create(50, source="AUDIT"),
    )
    evals_50 = evaluate_requirements(rules=[rule], character_state=char_50, evidence_map={"REQ_LVL52": True})
    assert evals_50[0].eligibility == EligibilityState.FUTURE
    assert evals_50[0].readiness == RequirementReadiness.UNKNOWN
    assert evals_50[0].is_active_blocker is False
    assert is_transition_ready(evals_50) is True

    char_52 = CharacterState(
        character_id="hero1",
        character_name="Merc",
        level=ProvenancedField[int].create(52, source="AUDIT"),
    )
    evals_52 = evaluate_requirements(rules=[rule], character_state=char_52, evidence_map={"REQ_LVL52": True})
    assert evals_52[0].eligibility == EligibilityState.ACTIVE
    assert evals_52[0].readiness == RequirementReadiness.SATISFIED
    assert is_transition_ready(evals_52) is True


def test_mixed_blockers_readiness_and_blocking_states() -> None:
    """Verify combined blocker states: SATISFIED + UNKNOWN = not ready, not blocked.
    SATISFIED + UNKNOWN + UNSATISFIED = not ready, blocked.
    """
    rule_a = GuideRule(
        id="RULE_A",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.API],
    )
    rule_b = GuideRule(
        id="RULE_B",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.API],
    )
    rule_c = GuideRule(
        id="RULE_C",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.API],
    )

    # 1. SATISFIED + UNKNOWN
    evals_mixed_1 = evaluate_requirements(
        rules=[rule_a, rule_b],
        evidence_map={"RULE_A": True, "RULE_B": None},
        character_level=52,
    )
    assert is_transition_ready(evals_mixed_1) is False
    assert has_unsatisfied_blocker(evals_mixed_1) is False
    assert has_unknown_blocker(evals_mixed_1) is True
    assert get_active_blocking_requirements(evals_mixed_1) == []

    # 2. SATISFIED + UNKNOWN + UNSATISFIED
    evals_mixed_2 = evaluate_requirements(
        rules=[rule_a, rule_b, rule_c],
        evidence_map={"RULE_A": True, "RULE_B": None, "RULE_C": False},
        character_level=52,
    )
    assert is_transition_ready(evals_mixed_2) is False
    assert has_unsatisfied_blocker(evals_mixed_2) is True
    assert len(get_active_blocking_requirements(evals_mixed_2)) == 1
    assert get_active_blocking_requirements(evals_mixed_2)[0].rule_id == "RULE_C"


def test_requirement_evaluation_is_immutable() -> None:
    """Verify RequirementEvaluation is frozen and rejects mutation."""
    ev = RequirementEvaluation(
        rule_id="RULE_FROZEN",
        rule_name="Frozen Rule",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
        readiness=RequirementReadiness.SATISFIED,
    )
    with pytest.raises(Exception):
        ev.readiness = RequirementReadiness.UNSATISFIED  # type: ignore[misc]

