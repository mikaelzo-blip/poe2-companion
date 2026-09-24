"""Unit tests for stage-aware resistance target policy resolution and models."""

import pytest
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.resistance import (
    ResistancePolicyMode,
    ResistanceTargetPolicy,
    ResistanceType,
    get_resistance_policy,
    resolve_resistance_policies,
)


def test_build_progression_stage_aliases():
    assert BuildProgressionStage("lvl 15-32") == BuildProgressionStage.LEVELING_15_32
    assert BuildProgressionStage("lvl 1-14") == BuildProgressionStage.LEVELING_1_14
    assert BuildProgressionStage("lvl 33-51") == BuildProgressionStage.LEVELING_33_51
    assert BuildProgressionStage("lvl 52 swap") == BuildProgressionStage.SWAP_52
    assert BuildProgressionStage("lvl 53-68") == BuildProgressionStage.LEVELING_53_68
    assert BuildProgressionStage("LEVELING_15_32") == BuildProgressionStage.LEVELING_15_32
    assert BuildProgressionStage.LEVELING_15_32.is_campaign is True
    assert BuildProgressionStage.LEVELING_15_32.is_pre_swap is True
    assert BuildProgressionStage.LEVELING_15_32.is_post_swap is False
    assert BuildProgressionStage.SWAP_52.is_campaign is True
    assert BuildProgressionStage.SWAP_52.is_pre_swap is False
    assert BuildProgressionStage.SWAP_52.is_post_swap is True
    assert BuildProgressionStage.EARLY_ENDGAME.is_campaign is False
    assert BuildProgressionStage.EARLY_ENDGAME.is_pre_swap is False
    assert BuildProgressionStage.EARLY_ENDGAME.is_post_swap is True


def test_fubgun_campaign_resistance_policy_has_no_hard_numeric_target():
    policy = get_resistance_policy(
        build_profile="fubgun",
        stage=BuildProgressionStage.LEVELING_15_32,
        res_type=ResistanceType.LIGHTNING,
    )
    assert policy.mode == ResistancePolicyMode.REFERENCE_ONLY
    assert policy.target_effective is None
    assert policy.reference_cap == 75
    assert policy.max_resistance == 75
    assert policy.is_hard_target is False
    assert "CAMPAIGN" in policy.source


def test_chaos_resistance_policy_reference_only_by_default():
    policy = get_resistance_policy(
        build_profile="fubgun",
        stage=BuildProgressionStage.LEVELING_15_32,
        res_type=ResistanceType.CHAOS,
    )
    assert policy.mode == ResistancePolicyMode.REFERENCE_ONLY
    assert policy.target_effective is None
    assert policy.is_hard_target is False


def test_resolve_resistance_policies_for_campaign():
    policies = resolve_resistance_policies(stage="lvl 15-32", build_profile="fubgun")
    for r_type in (ResistanceType.FIRE, ResistanceType.COLD, ResistanceType.LIGHTNING):
        pol = policies[r_type]
        assert pol.mode == ResistancePolicyMode.REFERENCE_ONLY
        assert pol.target_effective is None
        assert pol.reference_cap == 75
        assert pol.is_hard_target is False

    chaos_pol = policies[ResistanceType.CHAOS]
    assert chaos_pol.mode == ResistancePolicyMode.REFERENCE_ONLY
    assert chaos_pol.target_effective is None
    assert chaos_pol.is_hard_target is False


def test_explicit_user_hard_target_creates_hard_target():
    user_policy = ResistanceTargetPolicy(
        res_type=ResistanceType.LIGHTNING,
        mode=ResistancePolicyMode.USER_HARD_TARGET,
        target_effective=75,
        reference_cap=75,
        max_resistance=75,
        source="USER_EXPLICIT",
        verification="USER_VERIFIED",
    )
    assert user_policy.is_hard_target is True
    assert user_policy.target_effective == 75
