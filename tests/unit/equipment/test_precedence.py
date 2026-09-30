"""Unit tests for non-scalar verdict precedence rules."""

import pytest
from companion.equipment.rules import (
    BuildBreakerCertainty,
    BuildBreakerEvaluation,
    BuildProgressionStage,
    RuleSeverity,
)
from companion.equipment.requirements import RequirementCascadeResult, RequirementDeficiency
from companion.equipment.baseline import CharacterStatBaseline, CharacterFact
from companion.equipment.contextual_value import (
    evaluate_loadout_contextual_analysis,
)
from companion.equipment.data_sufficiency import (
    DataSufficiencyResult,
    RecommendationDataSufficiency,
)
from companion.equipment.precedence import (
    MultidimensionalComparison,
    Verdict,
    check_defense_regression,
    evaluate_contextual_verdict,
    evaluate_verdict_precedence,
)


def test_build_breaker_overrides_everything():
    breaker = BuildBreakerEvaluation(
        certainty=BuildBreakerCertainty.VERIFIED_BUILD_BREAKER,
        severity=RuleSeverity.BUILD_BREAKER,
        rule_name="FubgunOilGrenadeFireRule",
        reason="Adds flat fire to attacks",
    )
    reqs = RequirementCascadeResult(is_satisfied=True)

    verdict, reason, flags = evaluate_verdict_precedence(
        safety_eval=breaker,
        cascade_result=reqs,
        unmitigated_resistance_deficit=False,
    )
    assert verdict == Verdict.REJECT
    assert "BUILD_BREAKER" in flags


def test_requirement_failure_downgrades_to_conditional_upgrade():
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    req_fail = RequirementCascadeResult(
        is_satisfied=False,
        loadout_cascading_deficiencies=[
            RequirementDeficiency(
                target_type="equipped_item",
                target_name="Bow",
                attribute="dex",
                required_value=120,
                shortfall=20,
            )
        ],
        verdict_downgrade="CONDITIONAL_UPGRADE",
    )

    verdict, reason, flags = evaluate_verdict_precedence(
        safety_eval=safe,
        cascade_result=req_fail,
        unmitigated_resistance_deficit=False,
    )
    assert verdict == Verdict.CONDITIONAL_UPGRADE
    assert "REQUIREMENT_DEFICIENCY" in flags


def test_candidate_unrecoverable_requirement_failure_rejects():
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    candidate_req_fail = RequirementCascadeResult(
        is_satisfied=False,
        candidate_deficiencies=[
            RequirementDeficiency(
                target_type="candidate",
                target_name="Heavy Belt",
                attribute="str",
                required_value=150,
                shortfall=30,
            )
        ],
        verdict_downgrade="REJECT",
    )

    verdict, reason, flags = evaluate_verdict_precedence(
        safety_eval=safe,
        cascade_result=candidate_req_fail,
    )
    assert verdict == Verdict.REJECT
    assert "CANNOT_EQUIP_CANDIDATE" in flags


def test_high_risk_unknown_downgrades_equip_now():
    unknown_safety = BuildBreakerEvaluation(
        certainty=BuildBreakerCertainty.UNKNOWN_APPLICABILITY,
        severity=RuleSeverity.WARNING,
        rule_name="FubgunOilGrenadeFireRule",
        reason="Unknown fire applicability",
    )
    reqs = RequirementCascadeResult(is_satisfied=True)

    verdict, reason, flags = evaluate_verdict_precedence(
        safety_eval=unknown_safety,
        cascade_result=reqs,
        unmitigated_resistance_deficit=False,
    )
    assert verdict == Verdict.CONDITIONAL_UPGRADE
    assert "HIGH_RISK" in flags


def test_pure_positive_upgrade_yields_equip_now():
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)

    verdict, reason, flags = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
    )
    assert verdict == Verdict.EQUIP_NOW


def test_case_d_explicit_hard_target_unchanged_blocks_equip_now():
    """Case D (Hard Target): Candidate with large life but 0 resistance when character has verified hard target."""
    # Baseline with critical lightning resistance deficit (40% vs 75% target -> 35% deficit)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_d",
        character_id="char_d",
        anchored_loadout_revision=1,
        lightning_res=40,
        fire_res=75,
        cold_res=75,
        chaos_res=0,
        life=2000,
    )
    # Candidate provides no lightning res delta (unchanged deficit) under EARLY_ENDGAME hard target
    contextual_analysis = evaluate_loadout_contextual_analysis(
        baseline=baseline,
        delta_res={},
        stage=BuildProgressionStage.EARLY_ENDGAME,
    )
    assert contextual_analysis.has_unchanged_critical_deficiency is True

    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)

    verdict, reason, flags = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        contextual_analysis=contextual_analysis,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
    )

    assert verdict != Verdict.EQUIP_NOW
    assert verdict == Verdict.CONDITIONAL_UPGRADE
    assert "UNCHANGED_CRITICAL_DEFICIT" in flags


def test_case_d_campaign_reference_only_unchanged_permits_equip_now():
    """Case D (Campaign Reference Only): Leveling character with 40% lightning res is not blocked by reference cap."""
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_d_camp",
        character_id="char_d_camp",
        anchored_loadout_revision=1,
        lightning_res=40,
        fire_res=75,
        cold_res=75,
        chaos_res=0,
        life=2000,
    )
    # Campaign leveling stage (REFERENCE_ONLY policy)
    contextual_analysis = evaluate_loadout_contextual_analysis(
        baseline=baseline,
        delta_res={},
        stage=BuildProgressionStage.LEVELING_15_32,
    )
    assert contextual_analysis.has_unchanged_critical_deficiency is False

    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)

    verdict, reason, flags = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        contextual_analysis=contextual_analysis,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
    )

    assert verdict == Verdict.EQUIP_NOW
    assert "UNCHANGED_CRITICAL_DEFICIT" not in flags


def test_partial_safe_data_does_not_yield_equip_now():
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)
    partial = DataSufficiencyResult(
        sufficiency=RecommendationDataSufficiency.PARTIAL_SAFE,
        reasons=["Cold and Lightning Resistance are unobserved"],
        is_sufficient_for_equip_now=False,
    )

    verdict, reason, flags = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        data_sufficiency=partial,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
    )

    assert verdict != Verdict.EQUIP_NOW
    assert verdict == Verdict.INSUFFICIENT_DATA
    assert "INSUFFICIENT_DATA" in flags


def test_data_insufficiency_yields_insufficient_data():
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)
    insuff = DataSufficiencyResult(
        sufficiency=RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP,
        reasons=["Character stat baseline is missing"],
        is_sufficient_for_equip_now=False,
    )

    verdict, reason, flags = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        data_sufficiency=insuff,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
    )
    assert verdict == Verdict.INSUFFICIENT_DATA
    assert "INSUFFICIENT_DATA" in flags


def test_worsened_deficiency_yields_conditional_or_reject():
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_w",
        character_id="char_w",
        anchored_loadout_revision=1,
        fire_res=60,
    )
    # Delta -10 worsens fire deficit
    from companion.equipment.resistance import ResistanceType
    contextual_analysis = evaluate_loadout_contextual_analysis(
        baseline=baseline,
        delta_res={ResistanceType.FIRE: -10.0},
    )
    assert contextual_analysis.has_worsened_deficiency is True

    verdict, reason, flags = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        contextual_analysis=contextual_analysis,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
    )
    assert verdict in (Verdict.CONDITIONAL_UPGRADE, Verdict.REJECT)
    assert "WORSENS_DEFICIENCY" in flags


def test_created_deficiency_yields_conditional_or_reject():
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_c",
        character_id="char_c",
        anchored_loadout_revision=1,
        fire_res=75,
    )
    from companion.equipment.resistance import ResistanceType
    contextual_analysis = evaluate_loadout_contextual_analysis(
        baseline=baseline,
        delta_res={ResistanceType.FIRE: -15.0},
    )
    assert contextual_analysis.has_created_deficiency is True

    verdict, reason, flags = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        contextual_analysis=contextual_analysis,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
    )
    assert verdict in (Verdict.CONDITIONAL_UPGRADE, Verdict.REJECT)
    assert "CREATES_DEFICIENCY" in flags


def test_resolves_deficit_without_regression_yields_equip_now():
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_r",
        character_id="char_r",
        anchored_loadout_revision=1,
        fire_res=60,
    )
    from companion.equipment.resistance import ResistanceType
    contextual_analysis = evaluate_loadout_contextual_analysis(
        baseline=baseline,
        delta_res={ResistanceType.FIRE: +20.0},
    )
    assert contextual_analysis.has_resolved_deficiency is True
    assert contextual_analysis.has_worsened_deficiency is False
    assert contextual_analysis.has_created_deficiency is False

    verdict, reason, flags = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        contextual_analysis=contextual_analysis,
        comparison=MultidimensionalComparison.MIXED_TRADEOFF,
    )
    assert verdict == Verdict.EQUIP_NOW
    assert "RESOLVES_DEFICIT" in flags


def test_healthy_multidimensional_comparisons():
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)

    # Dominant improvement -> EQUIP_NOW
    v, _, _ = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
    )
    assert v == Verdict.EQUIP_NOW

    # Mixed tradeoff -> CONDITIONAL_UPGRADE or KEEP_FOR_LATER
    v, _, _ = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        comparison=MultidimensionalComparison.MIXED_TRADEOFF,
    )
    assert v in (Verdict.CONDITIONAL_UPGRADE, Verdict.KEEP_FOR_LATER)

    # No meaningful gain -> KEEP_FOR_LATER
    v, _, _ = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        comparison=MultidimensionalComparison.NO_MEANINGFUL_CURRENT_GAIN,
    )
    assert v == Verdict.KEEP_FOR_LATER

    # Clear downgrade -> REJECT
    v, _, _ = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        comparison=MultidimensionalComparison.CLEAR_DOWNGRADE,
    )
    assert v == Verdict.REJECT


def test_check_defense_regression_detection():
    # Negative delta on local defenses
    assert check_defense_regression(armour_delta=-100) is True
    assert check_defense_regression(evasion_delta=-50) is True
    assert check_defense_regression(es_delta=-1) is True

    # Mixed defense tradeoff: loses armour but gains evasion
    assert check_defense_regression(armour_delta=-800, evasion_delta=400) is True
    assert check_defense_regression(armour_delta=300, evasion_delta=-200) is True

    # Non-negative defenses
    assert check_defense_regression(armour_delta=100, evasion_delta=50, es_delta=0) is False
    assert check_defense_regression(0, 0, 0) is False


def test_defense_regression_blocks_clean_resolves_deficit():
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_r",
        character_id="char_r",
        anchored_loadout_revision=1,
        fire_res=60,
    )
    from companion.equipment.resistance import ResistanceType
    contextual_analysis = evaluate_loadout_contextual_analysis(
        baseline=baseline,
        delta_res={ResistanceType.FIRE: +20.0},
    )
    assert contextual_analysis.has_resolved_deficiency is True

    # With defense regression, candidate CANNOT qualify for clean RESOLVES_DEFICIT / EQUIP_NOW
    v, reason, flags = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        contextual_analysis=contextual_analysis,
        has_defense_regression=True,
        defense_tradeoff_reason="Candidate incurs regression on local defenses (Armour -800); represents a mixed defense tradeoff.",
    )
    assert v == Verdict.CONDITIONAL_UPGRADE
    assert "MIXED_TRADEOFF" in flags
    assert "RESOLVES_DEFICIT" not in flags
    assert "Armour -800" in reason


def test_defense_regression_blocks_clean_dominant_improvement():
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)

    # Dominant improvement with defense regression becomes MIXED_TRADEOFF / CONDITIONAL_UPGRADE
    v, reason, flags = evaluate_contextual_verdict(
        safety_eval=safe,
        cascade_result=reqs,
        comparison=MultidimensionalComparison.DOMINANT_IMPROVEMENT,
        has_defense_regression=True,
        defense_tradeoff_reason="Mixed defense tradeoff: loses Armour (-800) while gaining Evasion (+400).",
    )
    assert v == Verdict.CONDITIONAL_UPGRADE
    assert "MIXED_TRADEOFF" in flags
    assert "Armour (-800)" in reason


def test_defense_regression_in_evaluate_verdict_precedence():
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)

    v, reason, flags = evaluate_verdict_precedence(
        safety_eval=safe,
        cascade_result=reqs,
        has_defense_regression=True,
    )
    assert v == Verdict.CONDITIONAL_UPGRADE
    assert "MIXED_TRADEOFF" in flags
