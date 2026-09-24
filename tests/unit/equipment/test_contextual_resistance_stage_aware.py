"""Unit tests for stage-aware contextual resistance analysis (REFERENCE_ONLY vs HARD_TARGET)."""

import pytest
from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.contextual_value import (
    DeficiencyImpact,
    MarginalValueTier,
    evaluate_contextual_resistance,
    evaluate_loadout_contextual_analysis,
)
from companion.equipment.resistance import (
    ResistancePolicyMode,
    ResistanceTargetPolicy,
    ResistanceType,
)
from companion.equipment.rules import BuildProgressionStage


def test_reference_only_campaign_low_res_delta_zero_not_critical_deficiency():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b_low",
        character_id="c_low",
        anchored_loadout_revision=1,
        lightning_res=7,
        lightning_raw=7,
        max_lightning_res=75,
    )
    policy = ResistanceTargetPolicy(
        res_type=ResistanceType.LIGHTNING,
        mode=ResistancePolicyMode.REFERENCE_ONLY,
        target_effective=None,
        reference_cap=75,
        max_resistance=75,
        source="FUBGUN_CAMPAIGN_PRIORITY",
        verification="VERIFIED",
    )

    analysis = evaluate_contextual_resistance(
        baseline=baseline,
        res_type=ResistanceType.LIGHTNING,
        delta=0.0,
        target=policy,
    )

    assert analysis.is_hard_target is False
    assert analysis.deficit_before == 0
    assert analysis.deficit_after == 0
    assert analysis.gap_before == 68
    assert analysis.impact == DeficiencyImpact.UNCHANGED
    assert "priority" in analysis.reason.lower() or "unchanged" in analysis.reason.lower()


def test_reference_only_campaign_res_improvement_recognized():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b_low",
        character_id="c_low",
        anchored_loadout_revision=1,
        lightning_res=7,
        lightning_raw=7,
        max_lightning_res=75,
    )
    policy = ResistanceTargetPolicy(
        res_type=ResistanceType.LIGHTNING,
        mode=ResistancePolicyMode.REFERENCE_ONLY,
        target_effective=None,
        reference_cap=75,
        max_resistance=75,
        source="FUBGUN_CAMPAIGN_PRIORITY",
        verification="VERIFIED",
    )

    analysis = evaluate_contextual_resistance(
        baseline=baseline,
        res_type=ResistanceType.LIGHTNING,
        delta=+20.0,
        target=policy,
    )

    assert analysis.impact == DeficiencyImpact.IMPROVES
    assert analysis.tier in (MarginalValueTier.CRITICAL, MarginalValueTier.HIGH)
    assert analysis.projected_effective == 27
    assert analysis.gap_after == 48


def test_reference_only_campaign_res_regression_recognized_as_worsening():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b_reg",
        character_id="c_reg",
        anchored_loadout_revision=1,
        lightning_res=20,
        lightning_raw=20,
        max_lightning_res=75,
    )
    policy = ResistanceTargetPolicy(
        res_type=ResistanceType.LIGHTNING,
        mode=ResistancePolicyMode.REFERENCE_ONLY,
        target_effective=None,
        reference_cap=75,
        max_resistance=75,
        source="FUBGUN_CAMPAIGN_PRIORITY",
        verification="VERIFIED",
    )

    analysis = evaluate_contextual_resistance(
        baseline=baseline,
        res_type=ResistanceType.LIGHTNING,
        delta=-15.0,
        target=policy,
    )

    assert analysis.impact == DeficiencyImpact.WORSENS
    assert analysis.projected_effective == 5


def test_reference_only_capped_state_loss_creates_new_deficiency():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b_cap",
        character_id="c_cap",
        anchored_loadout_revision=1,
        lightning_res=75,
        lightning_raw=75,
        max_lightning_res=75,
    )
    policy = ResistanceTargetPolicy(
        res_type=ResistanceType.LIGHTNING,
        mode=ResistancePolicyMode.REFERENCE_ONLY,
        target_effective=None,
        reference_cap=75,
        max_resistance=75,
        source="FUBGUN_CAMPAIGN_PRIORITY",
        verification="VERIFIED",
    )

    analysis = evaluate_contextual_resistance(
        baseline=baseline,
        res_type=ResistanceType.LIGHTNING,
        delta=-30.0,
        target=policy,
    )

    assert analysis.impact == DeficiencyImpact.CREATES_NEW_DEFICIENCY
    assert analysis.tier == MarginalValueTier.CRITICAL
    assert analysis.projected_effective == 45


def test_loadout_contextual_analysis_campaign_stage_does_not_emit_unchanged_critical():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b_camp",
        character_id="c_camp",
        anchored_loadout_revision=1,
        fire_res=15,
        fire_raw=15,
        cold_res=0,
        cold_raw=0,
        lightning_res=7,
        lightning_raw=7,
        chaos_res=0,
        life=500,
    )

    analysis = evaluate_loadout_contextual_analysis(
        baseline=baseline,
        delta_res={},
        stage=BuildProgressionStage.LEVELING_15_32,
    )

    # In campaign, existing low resistances below reference cap are unresolved priorities,
    # NOT unchanged critical deficiencies that block EQUIP_NOW
    assert analysis.has_unchanged_critical_deficiency is False
    assert len(analysis.unresolved_resistance_priorities) > 0
