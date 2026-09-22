"""Unit tests for M4 Objective Candidate Generator."""

from __future__ import annotations

import pytest

from companion.build.delta import BuildDeltaResult
from companion.build.passives import PassiveDeltaEntry
from companion.build.policy import DeltaReason, DeltaStatus
from companion.build.progression import ProgressionPhase
from companion.build.skills import SkillGroupDeltaEntry
from companion.build.variants import (
    TargetVariant,
    TargetVariantResolution,
    VariantResolutionStatus,
)
from companion.objectives.generator import generate_objective_candidates
from companion.objectives.schema import (
    CostOfIgnoring,
    EvidenceTrustworthiness,
    ObjectiveHorizon,
    ObjectivePriority,
)
from companion.rules.schema import (
    GuideRule,
    SourceVerificationStatus,
    TransitionRuleRole,
)
from companion.sources.models_normalized import WeaponSetContext
from companion.state.provenance import ProvenancedField, VerificationState
from companion.state.schema import CharacterState
from companion.transition.requirements import RequirementEvaluation, RequirementReadiness
from companion.transition.state import Level52TransitionResult, Level52TransitionState


def _make_char_state(level: int = 52) -> CharacterState:
    char = CharacterState.create_initial("char_01", "TestChar")
    char.level = ProvenancedField.create(level, "test", VerificationState.VERIFIED)
    return char


def _make_empty_delta(char: CharacterState) -> BuildDeltaResult:
    return BuildDeltaResult(
        character_id=char.character_id,
        character_level=char.level.value,
        progression_phase=ProgressionPhase.POST_52_53_68,
        target_variant_resolution=TargetVariantResolution(
            variant=TargetVariant.NONE, status=VariantResolutionStatus.NOT_APPLICABLE
        ),
        target_stage_name="lvl 53-68",
    )


def test_transition_blocked_generates_hard_blocker():
    """M3 BLOCKED state generates a HARD_BLOCKER objective detailing unsatisfied blockers."""
    char = _make_char_state(52)
    delta = _make_empty_delta(char)
    req = RequirementEvaluation(
        rule_id="swap_lvl_52",
        rule_name="Level 52 Weapon Swap",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        readiness=RequirementReadiness.UNSATISFIED,
        source_status=SourceVerificationStatus.USABLE,
        reason="Weapon set 2 missing required cross-swap bow",
    )
    transition = Level52TransitionResult(
        character_id=char.character_id,
        character_level=52,
        state=Level52TransitionState.BLOCKED,
        requirements=[req],
        blocking_requirements=[req],
    )

    candidates = generate_objective_candidates(delta, transition, char)
    blockers = [c for c in candidates if c.priority == ObjectivePriority.HARD_BLOCKER]
    assert len(blockers) >= 1
    top_blocker = blockers[0]
    assert "swap_lvl_52" in top_blocker.id
    assert top_blocker.is_corrective is True
    assert len(top_blocker.action) > 0


def test_transition_verifying_generates_verification_requirement():
    """M3 VERIFYING state generates an audit task under TRANSITION_REQUIREMENT, never HARD_BLOCKER."""
    char = _make_char_state(52)
    delta = _make_empty_delta(char)
    req = RequirementEvaluation(
        rule_id="swap_lvl_52",
        rule_name="Level 52 Weapon Swap",
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        readiness=RequirementReadiness.UNKNOWN,
        source_status=SourceVerificationStatus.USABLE,
        reason="Equipment slot unobserved",
    )
    transition = Level52TransitionResult(
        character_id=char.character_id,
        character_level=52,
        state=Level52TransitionState.VERIFYING,
        requirements=[req],
        blocking_requirements=[req],
    )

    candidates = generate_objective_candidates(delta, transition, char)
    assert not any(c.priority == ObjectivePriority.HARD_BLOCKER for c in candidates)
    verifs = [c for c in candidates if c.priority == ObjectivePriority.TRANSITION_REQUIREMENT]
    assert len(verifs) >= 1
    assert verifs[0].is_corrective is False  # Observation/audit only!


def test_transition_complete_generates_zero_transition_objectives():
    """M3 COMPLETE state produces no transition objectives for historical level-52 swap."""
    char = _make_char_state(58)
    delta = _make_empty_delta(char)
    transition = Level52TransitionResult(
        character_id=char.character_id,
        character_level=58,
        state=Level52TransitionState.COMPLETE,
        requirement_evaluations=[],
    )

    candidates = generate_objective_candidates(delta, transition, char)
    assert not any("transition" in c.id for c in candidates)


def test_missing_passive_generates_current_progression():
    """M2 MISSING passive generates CURRENT_PROGRESSION objective with is_corrective=True."""
    char = _make_char_state(25)
    delta = _make_empty_delta(char)
    delta_with_passive = delta.model_copy(
        update={
            "passives": [
                PassiveDeltaEntry(
                    key=("strength36", WeaponSetContext.DEFAULT_OR_SHARED),
                    passive_id="strength36",
                    weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
                    status=DeltaStatus.MISSING,
                    required_count=1,
                )
            ]
        }
    )

    candidates = generate_objective_candidates(delta_with_passive, None, char)
    prog = [c for c in candidates if c.priority == ObjectivePriority.CURRENT_PROGRESSION]
    assert len(prog) >= 1
    assert "strength36" in prog[0].id
    assert prog[0].is_corrective is True


def test_uncertainty_preservation_unknown_passive_generates_audit_not_corrective():
    """M2 UNKNOWN passive generates audit objective with is_corrective=False, never corrective."""
    char = _make_char_state(25)
    delta = _make_empty_delta(char)
    delta_with_unknown = delta.model_copy(
        update={
            "passives": [
                PassiveDeltaEntry(
                    key=("fire62", WeaponSetContext.DEFAULT_OR_SHARED),
                    passive_id="fire62",
                    weapon_set_context=WeaponSetContext.DEFAULT_OR_SHARED,
                    status=DeltaStatus.UNKNOWN,
                    reason=DeltaReason.PARTIAL_PLAYER_OBSERVATION,
                    required_count=1,
                )
            ]
        }
    )

    candidates = generate_objective_candidates(delta_with_unknown, None, char)
    # Must NOT advise allocating node!
    assert not any(c.is_corrective for c in candidates)
    audits = [c for c in candidates if "fire62" in c.id]
    assert len(audits) >= 1
    assert audits[0].is_corrective is False
    assert audits[0].evidence_trust == EvidenceTrustworthiness.STALE_OR_UNKNOWN


def test_future_requirement_cast_on_dodge_isolated_as_future_preparation():
    """Future requirement like Cast on Dodge [58, 100] at level 52 generates FUTURE_PREPARATION, never blocker."""
    char = _make_char_state(52)
    delta = _make_empty_delta(char)
    delta_with_future_skill = delta.model_copy(
        update={
            "skills": [
                SkillGroupDeltaEntry(
                    logical_key=("Cast on Dodge", None),
                    primary_gem_id="Cast on Dodge",
                    status=DeltaStatus.FUTURE,
                    reason=DeltaReason.INELIGIBLE_LEVEL,
                    is_meta_gem=True,
                )
            ]
        }
    )

    candidates = generate_objective_candidates(delta_with_future_skill, None, char)
    assert not any(c.priority == ObjectivePriority.HARD_BLOCKER for c in candidates)
    future_cands = [c for c in candidates if c.priority == ObjectivePriority.FUTURE_PREPARATION]
    assert len(future_cands) >= 1
    assert future_cands[0].horizon == ObjectiveHorizon.FUTURE


def test_unresolved_high_end_variant_generates_variant_selection():
    """High-end progression with unresolved variant produces a target-selection objective, never assumes LVL85."""
    char = _make_char_state(85)
    delta = _make_empty_delta(char).model_copy(
        update={
            "progression_phase": ProgressionPhase.HIGH_END,
            "target_variant_resolution": TargetVariantResolution(
                variant=None,
                status=VariantResolutionStatus.UNRESOLVED,
                reason="NO_EXPLICIT_HIGH_END_VARIANT",
            ),
        }
    )

    candidates = generate_objective_candidates(delta, None, char)
    variant_cands = [c for c in candidates if "variant_selection" in c.id]
    assert len(variant_cands) == 1
    assert variant_cands[0].priority in (
        ObjectivePriority.HARD_BLOCKER,
        ObjectivePriority.CURRENT_PROGRESSION,
    )
    assert "Select target variant" in variant_cands[0].action


def test_no_fabricated_survival_risk_without_authoritative_rule():
    """No SURVIVAL_RISK candidate is generated unless backed by an authoritative usable rule."""
    char = _make_char_state(52)
    delta = _make_empty_delta(char)

    candidates = generate_objective_candidates(delta, None, char, rules=[])
    assert not any(c.priority == ObjectivePriority.SURVIVAL_RISK for c in candidates)


def test_unverified_heuristics_cannot_emit_gating_objectives():
    """Labeled inferences or non-usable rules cannot generate high-severity objectives."""
    char = _make_char_state(52)
    delta = _make_empty_delta(char)
    heuristic_rule = GuideRule(
        id="heuristic_res_curve",
        name="Heuristic Act Scaling",
        source_status=SourceVerificationStatus.PENDING_SOURCE_VERIFICATION,
        evaluable=True,
        description="Invented resistance curve",
    )
    candidates = generate_objective_candidates(delta, None, char, rules=[heuristic_rule])
    assert not any(
        c.priority
        in (
            ObjectivePriority.CRITICAL_MECHANIC_BREAK,
            ObjectivePriority.HARD_BLOCKER,
            ObjectivePriority.SURVIVAL_RISK,
        )
        for c in candidates
    )
