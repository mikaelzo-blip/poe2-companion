"""Golden scenario tests for M4 Objective Engine end-to-end evaluation."""

from __future__ import annotations

from pathlib import Path
import pytest

from companion.objectives.runner import run_objective_pipeline
from companion.objectives.schema import ObjectivePriority
from companion.rules.schema import (
    GuideRule,
    ObservabilityMethod,
    RequirementType,
    RuleSourceType,
    SourceVerificationStatus,
    TransitionRuleRole,
)
from companion.state.provenance import ProvenancedField, VerificationState
from companion.state.schema import CharacterState
from companion.transition.requirements import RequirementEvaluation, RequirementReadiness
from companion.transition.state import Level52TransitionRecord, Level52TransitionState


def test_golden_level_1_starting_character() -> None:
    """Level 1 character generates current progression objectives for starting skills/passives."""
    char = CharacterState.create_initial("hero_lvl_1", "Lvl1Hero")
    res = run_objective_pipeline(char, builds_dir="data/source/builds")
    assert res.status == "ACTIONABLE"
    assert res.primary_objective is not None
    assert res.primary_objective.priority in (
        ObjectivePriority.CURRENT_PROGRESSION,
        ObjectivePriority.STRONG_UPGRADE,
    )
    assert len(res.all_objectives) > 0


def test_golden_level_51_preparing_transition() -> None:
    """Level 51 character with usable preparation rule generates transition preparation objective."""
    char = CharacterState.create_initial("hero_lvl_51", "Lvl51Hero")
    char.level = ProvenancedField.create(51, "test", VerificationState.VERIFIED)

    res = run_objective_pipeline(char, builds_dir="data/source/builds")
    assert res.status == "ACTIONABLE"
    assert res.primary_objective is not None


def test_golden_level_52_blocked_transition() -> None:
    """Level 52 character with unsatisfied transition blocker emits HARD_BLOCKER as top objective."""
    char = CharacterState.create_initial("hero_lvl_52_blocked", "Lvl52Blocked")
    char.level = ProvenancedField.create(52, "test", VerificationState.VERIFIED)

    blocker = GuideRule(
        id="SWAP_WEAPONS_READY",
        name="Swap Weapons Slotted",
        provenance=RuleSourceType.BLUEPRINT_V2,
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        requirement_type=RequirementType.EQUIPMENT,
        min_level=52,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )

    res = run_objective_pipeline(
        char,
        builds_dir="data/source/builds",
        rules=[blocker],
        evidence_map={"SWAP_WEAPONS_READY": False},
    )
    assert res.status == "ACTIONABLE"
    assert res.primary_objective is not None
    assert res.primary_objective.priority == ObjectivePriority.HARD_BLOCKER
    assert "transition:level52:blocked" in res.primary_objective.id


def test_golden_level_52_ready_transition() -> None:
    """Level 52 character with all blocking requirements satisfied emits READY swap action."""
    char = CharacterState.create_initial("hero_lvl_52_ready", "Lvl52Ready")
    char.level = ProvenancedField.create(52, "test", VerificationState.VERIFIED)

    char.transition = Level52TransitionRecord(
        state=Level52TransitionState.READY,
        character_level=52,
        history=[],
    )

    res = run_objective_pipeline(char, builds_dir="data/source/builds")
    assert res.status == "ACTIONABLE"
    assert res.primary_objective is not None
    assert res.primary_objective.priority == ObjectivePriority.TRANSITION_REQUIREMENT
    assert res.primary_objective.id == "transition:level52:ready"


def test_golden_level_53_post_transition_complete() -> None:
    """Level 53 character post-swap with transition COMPLETE does not generate transition objectives."""
    char = CharacterState.create_initial("hero_lvl_53", "Lvl53Hero")
    char.level = ProvenancedField.create(53, "test", VerificationState.VERIFIED)

    char.transition = Level52TransitionRecord(
        state=Level52TransitionState.COMPLETE,
        character_level=53,
        history=[],
    )

    res = run_objective_pipeline(char, builds_dir="data/source/builds")
    assert res.status == "ACTIONABLE"
    # Ensure no transition objectives are present
    for obj in res.all_objectives:
        assert not obj.id.startswith("transition:")


def test_golden_level_85_unresolved_variant() -> None:
    """Level 85+ character without variant selection emits target variant selection objective."""
    char = CharacterState.create_initial("hero_lvl_85", "Lvl85Hero")
    char.level = ProvenancedField.create(85, "test", VerificationState.VERIFIED)

    char.transition = Level52TransitionRecord(
        state=Level52TransitionState.COMPLETE,
        character_level=85,
        history=[],
    )

    res = run_objective_pipeline(char, builds_dir="data/source/builds")
    assert res.status == "ACTIONABLE"
    variant_objs = [o for o in res.all_objectives if o.id == "build:target_variant_selection"]
    assert len(variant_objs) == 1
    assert variant_objs[0].priority == ObjectivePriority.CURRENT_PROGRESSION
