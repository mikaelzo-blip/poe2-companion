"""Unit tests for build-breaker rule schemas and certainty states."""

import pytest
from companion.equipment.rules import (
    RuleSeverity,
    BuildBreakerCertainty,
    BuildModifierFamily,
    BuildProgressionStage,
    BuildBreakerEvaluation,
)


def test_rule_schema_enums_and_evaluation():
    assert BuildBreakerCertainty.VERIFIED_SAFE == "VERIFIED_SAFE"
    assert BuildBreakerCertainty.VERIFIED_BUILD_BREAKER == "VERIFIED_BUILD_BREAKER"
    assert BuildBreakerCertainty.UNKNOWN_APPLICABILITY == "UNKNOWN_APPLICABILITY"

    eval_result = BuildBreakerEvaluation(
        certainty=BuildBreakerCertainty.VERIFIED_BUILD_BREAKER,
        severity=RuleSeverity.BUILD_BREAKER,
        rule_name="FubgunOilGrenadeFireRule",
        reason="Adds flat fire damage to attacks.",
    )
    assert eval_result.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER
    assert eval_result.severity == RuleSeverity.BUILD_BREAKER
