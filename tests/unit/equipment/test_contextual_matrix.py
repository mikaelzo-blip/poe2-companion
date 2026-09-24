"""Unit tests for contextual matrix across characters and baseline states."""

import pytest
from companion.equipment.schema import SlotType
from companion.equipment.baseline import CharacterStatBaseline, CharacterFact
from companion.equipment.contextual_value import (
    DeficiencyImpact,
    MarginalValueTier,
    evaluate_contextual_resistance,
    evaluate_contextual_attribute,
    evaluate_loadout_contextual_analysis,
)
from companion.equipment.resistance import ResistanceType, ResistanceTarget
from companion.equipment.data_sufficiency import (
    analyze_data_sufficiency,
    DataSufficiencyResult,
    RecommendationDataSufficiency,
)
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.parser import parse_item_text
from companion.equipment.precedence import (
    MultidimensionalComparison,
    Verdict,
    evaluate_contextual_verdict,
)
from companion.equipment.rules import (
    BuildBreakerCertainty,
    BuildBreakerEvaluation,
    BuildProgressionStage,
)
from companion.equipment.requirements import RequirementCascadeResult
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.loadout_cli import run_loadout_set_item, run_loadout_finalize
from companion.equipment.baseline_cli import run_baseline_set


def test_matrix_test_1_resistance_same_item_different_character():
    """Test 1: Resistance same item / different character (30% vs 105% raw)."""
    # Character A: In deficit (30% raw vs 75% cap) -> +30% resistance has HIGH or CRITICAL marginal value.
    baseline_a = CharacterStatBaseline.create_partial(
        baseline_id="base_a",
        character_id="char_a",
        anchored_loadout_revision=1,
        fire_res=30,
        fire_raw=30,
        max_fire_res=75,
    )
    res_a = evaluate_contextual_resistance(baseline_a, ResistanceType.FIRE, delta=30.0)
    assert res_a.impact == DeficiencyImpact.IMPROVES
    assert res_a.tier in (MarginalValueTier.HIGH, MarginalValueTier.CRITICAL)

    # Character B: Overcapped (105% raw vs 75% cap) -> +30% resistance has LOW or NO_IMMEDIATE_VALUE.
    baseline_b = CharacterStatBaseline.create_partial(
        baseline_id="base_b",
        character_id="char_b",
        anchored_loadout_revision=1,
        fire_res=75,
        fire_raw=105,
        max_fire_res=75,
    )
    res_b = evaluate_contextual_resistance(baseline_b, ResistanceType.FIRE, delta=30.0)
    assert res_b.impact == DeficiencyImpact.UNCHANGED
    assert res_b.tier in (MarginalValueTier.LOW, MarginalValueTier.NO_IMMEDIATE_VALUE)


def test_matrix_test_2_attribute_same_item_different_character():
    """Test 2: Attribute same item / different character (Dex 88/95 vs Dex 180/95)."""
    # Character A: Dex 88/95 (7 deficit). Candidate +10 Dex -> resolves deficit -> CRITICAL or HIGH.
    baseline_a = CharacterStatBaseline.create_partial(
        baseline_id="base_a",
        character_id="char_a",
        anchored_loadout_revision=1,
        dexterity=88,
    )
    attr_a = evaluate_contextual_attribute(baseline_a, "dex", delta=10.0, highest_required=95)
    assert attr_a.impact == DeficiencyImpact.RESOLVES
    assert attr_a.tier in (MarginalValueTier.CRITICAL, MarginalValueTier.HIGH)

    # Character B: Dex 180/95 (85 surplus). Candidate +10 Dex -> UNCHANGED -> LOW.
    baseline_b = CharacterStatBaseline.create_partial(
        baseline_id="base_b",
        character_id="char_b",
        anchored_loadout_revision=1,
        dexterity=180,
    )
    attr_b = evaluate_contextual_attribute(baseline_b, "dex", delta=10.0, highest_required=95)
    assert attr_b.impact == DeficiencyImpact.UNCHANGED
    assert attr_b.tier == MarginalValueTier.LOW


def test_matrix_test_3_critical_deficit_case_d():
    """Test 3: Critical deficit Case D (Candidate A +45 Lightning vs Candidate B +0 Lightning, +100 Life on Lightning 30/75 character).

    Candidate B must NOT receive EQUIP_NOW (CONDITIONAL_UPGRADE or KEEP_FOR_LATER).
    """
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_case_d",
        character_id="char_case_d",
        anchored_loadout_revision=1,
        lightning_res=30,
        lightning_raw=30,
        max_lightning_res=75,
        fire_res=75,
        fire_raw=80,
        max_fire_res=75,
        cold_res=75,
        cold_raw=80,
        max_cold_res=75,
        life=2000,
    )
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)

    # Candidate A: +45 Lightning Res (cures 45% deficit) -> resolves critical deficit -> EQUIP_NOW
    analysis_a = evaluate_loadout_contextual_analysis(
        baseline=baseline,
        delta_res={ResistanceType.LIGHTNING: 45.0},
        stage=BuildProgressionStage.EARLY_ENDGAME,
    )
    assert analysis_a.has_resolved_deficiency is True
    assert analysis_a.has_unchanged_critical_deficiency is False
    verdict_a, _, _ = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        contextual_analysis=analysis_a,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
    )
    assert verdict_a == Verdict.EQUIP_NOW

    # Candidate B: +0 Lightning Res, +100 Life on Lightning 30/75 character -> unchanged critical deficit.
    # Must NOT receive EQUIP_NOW (resolves to CONDITIONAL_UPGRADE or KEEP_FOR_LATER).
    analysis_b = evaluate_loadout_contextual_analysis(
        baseline=baseline,
        delta_res={ResistanceType.LIGHTNING: 0.0},
        stage=BuildProgressionStage.EARLY_ENDGAME,
    )
    assert analysis_b.has_critical_deficiency is True
    assert analysis_b.has_unchanged_critical_deficiency is True

    verdict_b, _, flags_b = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        contextual_analysis=analysis_b,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
    )
    assert verdict_b != Verdict.EQUIP_NOW
    assert verdict_b in (Verdict.CONDITIONAL_UPGRADE, Verdict.KEEP_FOR_LATER)
    assert "UNCHANGED_CRITICAL_DEFICIT" in flags_b


def test_matrix_test_3_campaign_candidate_b_not_blocked():
    """Test 3 (Campaign): Leveling character with 30/75 lightning res and candidate with 0 res + 100 life.

    Under campaign stage (REFERENCE_ONLY), Candidate B is NOT blocked by reference cap.
    """
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_case_d_camp",
        character_id="char_case_d_camp",
        anchored_loadout_revision=1,
        lightning_res=30,
        lightning_raw=30,
        max_lightning_res=75,
        fire_res=75,
        fire_raw=80,
        max_fire_res=75,
        cold_res=75,
        cold_raw=80,
        max_cold_res=75,
        life=2000,
    )
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)

    analysis_b = evaluate_loadout_contextual_analysis(
        baseline=baseline,
        delta_res={ResistanceType.LIGHTNING: 0.0},
        stage=BuildProgressionStage.LEVELING_15_32,
    )
    assert analysis_b.has_critical_deficiency is False
    assert analysis_b.has_unchanged_critical_deficiency is False

    verdict_b, _, flags_b = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        contextual_analysis=analysis_b,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
    )
    assert verdict_b == Verdict.EQUIP_NOW
    assert "UNCHANGED_CRITICAL_DEFICIT" not in flags_b


def test_matrix_test_4_healthy_character_candidates():
    """Test 4: Healthy character:

    - Candidate C: verified Life + Movement improvement, no regression -> EQUIP_NOW.
    - Candidate D: mixed Life gain + resistance loss while safe -> contextual tradeoff (CONDITIONAL_UPGRADE or KEEP_FOR_LATER).
    - Candidate E: no meaningful current benefit -> KEEP_FOR_LATER.
    - Candidate F: clear verified downgrade -> REJECT.
    """
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_healthy",
        character_id="char_healthy",
        anchored_loadout_revision=1,
        fire_res=75,
        fire_raw=90,
        max_fire_res=75,
        cold_res=75,
        cold_raw=90,
        max_cold_res=75,
        lightning_res=75,
        lightning_raw=90,
        max_lightning_res=75,
        chaos_res=20,
        life=3000,
        movement_speed=10,
    )
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)

    # Candidate C: Dominant improvement (verified Life + Movement speed gain, no regression) -> EQUIP_NOW
    analysis_c = evaluate_loadout_contextual_analysis(
        baseline=baseline,
        delta_res={ResistanceType.FIRE: 0.0, ResistanceType.COLD: 0.0, ResistanceType.LIGHTNING: 0.0},
    )
    verdict_c, _, _ = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        contextual_analysis=analysis_c,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
    )
    assert verdict_c == Verdict.EQUIP_NOW

    # Candidate D: Mixed Life gain + resistance loss while safe -> MIXED_TRADEOFF -> CONDITIONAL_UPGRADE or KEEP_FOR_LATER
    # (e.g. fire res drops by 10, staying at 80 raw >= 75 cap, so safe, but trading res for life)
    analysis_d = evaluate_loadout_contextual_analysis(
        baseline=baseline,
        delta_res={ResistanceType.FIRE: -10.0},
    )
    assert analysis_d.has_created_deficiency is False
    assert analysis_d.has_worsened_deficiency is False
    verdict_d, _, _ = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        contextual_analysis=analysis_d,
        comparison=MultidimensionalComparison.MIXED_TRADEOFF,
    )
    assert verdict_d in (Verdict.CONDITIONAL_UPGRADE, Verdict.KEEP_FOR_LATER)

    # Candidate E: No meaningful current benefit -> NO_MEANINGFUL_CURRENT_GAIN -> KEEP_FOR_LATER
    verdict_e, _, _ = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        contextual_analysis=analysis_c,
        comparison=MultidimensionalComparison.NO_MEANINGFUL_CURRENT_GAIN,
    )
    assert verdict_e == Verdict.KEEP_FOR_LATER

    # Candidate F: Clear verified downgrade -> CLEAR_DOWNGRADE -> REJECT
    verdict_f, _, _ = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        contextual_analysis=analysis_c,
        comparison=MultidimensionalComparison.CLEAR_DOWNGRADE,
    )
    assert verdict_f == Verdict.REJECT


def test_matrix_test_5_missing_or_stale_baseline_gate():
    """Test 5: Missing / stale baseline gate:

    Missing baseline or stale baseline prevents confident EQUIP_NOW, emitting INSUFFICIENT_DATA or CONDITIONAL_UPGRADE.
    """
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)
    sample_boots = "Item Class: Boots\nRarity: Rare\nTest Boots\n--------\nRequirements:\nLevel: 45\n--------\n+30 to maximum Life\n"
    cand = parse_item_text(sample_boots, target_slot=SlotType.BOOTS)
    loadout = EquippedLoadout.create_draft(character_id="test")
    loadout.set_slot(SlotType.BOOTS, cand)
    loadout.finalize(loadout_id="l1")

    # Missing baseline
    suff_missing = analyze_data_sufficiency(
        baseline=None,
        loadout=loadout,
        candidate=cand,
        slot=SlotType.BOOTS,
        safety_eval=safe,
    )
    assert suff_missing.is_sufficient_for_equip_now is False
    assert suff_missing.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP

    verdict_missing, _, _ = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        data_sufficiency=suff_missing,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
    )
    assert verdict_missing != Verdict.EQUIP_NOW
    assert verdict_missing in (Verdict.INSUFFICIENT_DATA, Verdict.CONDITIONAL_UPGRADE)

    # Stale baseline (e.g. revision mismatch between baseline and loadout)
    stale_baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_stale",
        character_id="test",
        anchored_loadout_revision=1,
        life=1500,
    )
    loadout_rev2 = EquippedLoadout.create_draft(character_id="test")
    loadout_rev2.set_slot(SlotType.BOOTS, cand)
    loadout_rev2.finalize(loadout_id="l2")
    loadout_rev2.revision = 2
    suff_stale = analyze_data_sufficiency(
        baseline=stale_baseline,
        loadout=loadout_rev2,  # mismatched revision -> stale
        candidate=cand,
        slot=SlotType.BOOTS,
        safety_eval=safe,
    )
    assert suff_stale.is_sufficient_for_equip_now is False
    assert suff_stale.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP

    verdict_stale, _, _ = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        data_sufficiency=suff_stale,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
    )
    assert verdict_stale != Verdict.EQUIP_NOW
    assert verdict_stale in (Verdict.INSUFFICIENT_DATA, Verdict.CONDITIONAL_UPGRADE)
