"""Unit tests for non-scalar verdict precedence rules."""

import pytest
from companion.equipment.rules import BuildBreakerCertainty, BuildBreakerEvaluation, RuleSeverity
from companion.equipment.requirements import RequirementCascadeResult, RequirementDeficiency
from companion.equipment.precedence import (
    Verdict,
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
        score_delta=+100.0,
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
        score_delta=+80.0,
        safety_eval=safe,
        cascade_result=req_fail,
        unmitigated_resistance_deficit=False,
    )
    assert verdict == Verdict.CONDITIONAL_UPGRADE
    assert "REQUIREMENT_DEFICIENCY" in flags


def test_high_risk_unknown_downgrades_equip_now():
    unknown_safety = BuildBreakerEvaluation(
        certainty=BuildBreakerCertainty.UNKNOWN_APPLICABILITY,
        severity=RuleSeverity.WARNING,
        rule_name="FubgunOilGrenadeFireRule",
        reason="Unknown fire applicability",
    )
    reqs = RequirementCascadeResult(is_satisfied=True)

    verdict, reason, flags = evaluate_verdict_precedence(
        score_delta=+90.0,
        safety_eval=unknown_safety,
        cascade_result=reqs,
        unmitigated_resistance_deficit=False,
    )
    assert verdict == Verdict.CONDITIONAL_UPGRADE
    assert "HIGH_RISK" in flags


def test_pure_positive_upgrade_yields_equip_now():
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)
    reqs = RequirementCascadeResult(is_satisfied=True)

    verdict, reason, flags = evaluate_verdict_precedence(
        score_delta=+50.0,
        safety_eval=safe,
        cascade_result=reqs,
        unmitigated_resistance_deficit=False,
    )
    assert verdict == Verdict.EQUIP_NOW
