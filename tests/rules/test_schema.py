"""Unit tests for declarative guide rule schema, enums, and models."""

import pytest
from pydantic import ValidationError

from companion.rules.schema import (
    SUPPORTED_OBSERVABILITY_METHODS,
    GuideRule,
    ObservabilityMethod,
    RequirementType,
    RuleEvaluationState,
    RuleSourceType,
    SourceVerificationStatus,
    TransitionRuleRole,
)


def test_rule_source_type_enum() -> None:
    """Verify RuleSourceType enum members and strict enforcement."""
    assert RuleSourceType.BLUEPRINT_V2 == "BLUEPRINT_V2"
    assert RuleSourceType.FUBGUN_BUILD == "FUBGUN_BUILD"
    assert RuleSourceType.WRITTEN_GUIDE == "WRITTEN_GUIDE"
    assert RuleSourceType.POB2_REFERENCE == "POB2_REFERENCE"
    assert RuleSourceType.LABELED_INFERENCE == "LABELED_INFERENCE"
    assert RuleSourceType.PENDING_SOURCE_VERIFICATION == "PENDING_SOURCE_VERIFICATION"

    with pytest.raises(ValueError):
        RuleSourceType("INVALID_SOURCE")


def test_source_verification_status_enum() -> None:
    """Verify SourceVerificationStatus enum members and strict enforcement."""
    assert SourceVerificationStatus.USABLE == "USABLE"
    assert SourceVerificationStatus.PENDING_SOURCE_VERIFICATION == "PENDING_SOURCE_VERIFICATION"
    assert SourceVerificationStatus.UNAVAILABLE == "UNAVAILABLE"

    with pytest.raises(ValueError):
        SourceVerificationStatus("CONFIRMED")
    with pytest.raises(ValueError):
        SourceVerificationStatus("INVALID_STATUS")


def test_observability_method_enum() -> None:
    """Verify ObservabilityMethod enum members and strict enforcement."""
    assert ObservabilityMethod.API == "API"
    assert ObservabilityMethod.GEAR_AUDIT == "GEAR_AUDIT"
    assert ObservabilityMethod.SKILL_AUDIT == "SKILL_AUDIT"
    assert ObservabilityMethod.PASSIVE_AUDIT == "PASSIVE_AUDIT"
    assert ObservabilityMethod.VISION == "VISION"
    assert ObservabilityMethod.MANUAL == "MANUAL"

    with pytest.raises(ValueError):
        ObservabilityMethod("INVALID_METHOD")


def test_rule_evaluation_state_enum() -> None:
    """Verify RuleEvaluationState enum members and strict enforcement."""
    assert RuleEvaluationState.PASS == "PASS"
    assert RuleEvaluationState.FAIL == "FAIL"
    assert RuleEvaluationState.UNKNOWN == "UNKNOWN"
    assert RuleEvaluationState.NOT_APPLICABLE == "NOT_APPLICABLE"
    assert RuleEvaluationState.STALE == "STALE"
    assert RuleEvaluationState.CONFLICTING_EVIDENCE == "CONFLICTING_EVIDENCE"

    with pytest.raises(ValueError):
        RuleEvaluationState("INVALID_STATE")


def test_requirement_type_enum() -> None:
    """Verify RequirementType enum members and strict enforcement."""
    assert RequirementType.EQUIPMENT == "EQUIPMENT"
    assert RequirementType.ITEM == "ITEM"
    assert RequirementType.SKILL == "SKILL"
    assert RequirementType.GEM == "GEM"
    assert RequirementType.PASSIVE == "PASSIVE"
    assert RequirementType.LEVEL == "LEVEL"
    assert RequirementType.STAT == "STAT"
    assert RequirementType.FLASK == "FLASK"
    assert RequirementType.GENERAL == "GENERAL"

    with pytest.raises(ValueError):
        RequirementType("INVALID_REQ_TYPE")


def test_transition_rule_role_enum() -> None:
    """Verify TransitionRuleRole enum members and strict enforcement."""
    assert TransitionRuleRole.BLOCKING_REQUIREMENT == "BLOCKING_REQUIREMENT"
    assert TransitionRuleRole.COMPLETION_EVIDENCE == "COMPLETION_EVIDENCE"
    assert TransitionRuleRole.ADVISORY == "ADVISORY"
    assert TransitionRuleRole.PREPARATION == "PREPARATION"

    with pytest.raises(ValueError):
        TransitionRuleRole("INVALID_ROLE")


def test_guide_rule_schema_validation_and_defaults() -> None:
    """Verify GuideRule instantiation with valid fields and defaults."""
    rule = GuideRule(
        id="RULE_01",
        name="Test Rule",
        description="A test rule description",
        provenance=RuleSourceType.BLUEPRINT_V2,
        status="USABLE",
        requirement_type=RequirementType.EQUIPMENT,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        observable_via=[ObservabilityMethod.API, ObservabilityMethod.GEAR_AUDIT],
    )

    assert rule.id == "RULE_01"
    assert rule.name == "Test Rule"
    assert rule.description == "A test rule description"
    assert rule.provenance == RuleSourceType.BLUEPRINT_V2
    assert rule.source_type == RuleSourceType.BLUEPRINT_V2
    assert rule.source_status == SourceVerificationStatus.USABLE
    assert rule.status == SourceVerificationStatus.USABLE
    assert rule.requirement_type == RequirementType.EQUIPMENT
    assert rule.transition_role == TransitionRuleRole.BLOCKING_REQUIREMENT
    assert rule.observable_via == [ObservabilityMethod.API, ObservabilityMethod.GEAR_AUDIT]
    assert rule.evaluable is True


def test_guide_rule_strict_enum_validation() -> None:
    """Verify GuideRule raises ValidationError on invalid enum inputs."""
    with pytest.raises(ValidationError):
        GuideRule(
            id="RULE_BAD_STATUS",
            status="NON_EXISTENT_STATUS",
            observable_via=[ObservabilityMethod.API],
        )

    with pytest.raises(ValidationError):
        GuideRule(
            id="RULE_BAD_ROLE",
            transition_role="INVALID_ROLE",
            observable_via=[ObservabilityMethod.API],
        )

    with pytest.raises(ValidationError):
        GuideRule(
            id="RULE_BAD_REQ",
            requirement_type="INVALID_REQ",
            observable_via=[ObservabilityMethod.API],
        )

    with pytest.raises(ValidationError):
        GuideRule(
            id="RULE_BAD_METHOD",
            observable_via=["INVALID_OBS_METHOD"],
        )


def test_transition_role_decoupling_from_requirement_type() -> None:
    """Verify transition_role is decoupled from requirement_type.

    An EQUIPMENT requirement must be able to hold any TransitionRuleRole,
    and a SKILL requirement must also be able to hold any TransitionRuleRole.
    The transition_role must NEVER be inferred implicitly from requirement_type.
    """
    roles = [
        TransitionRuleRole.BLOCKING_REQUIREMENT,
        TransitionRuleRole.COMPLETION_EVIDENCE,
        TransitionRuleRole.PREPARATION,
        TransitionRuleRole.ADVISORY,
    ]

    for req_type in [RequirementType.EQUIPMENT, RequirementType.SKILL, RequirementType.PASSIVE]:
        for role in roles:
            rule = GuideRule(
                id=f"RULE_{req_type.value}_{role.value}",
                requirement_type=req_type,
                transition_role=role,
                observable_via=[ObservabilityMethod.API],
            )
            assert rule.requirement_type == req_type
            assert rule.transition_role == role

    # Without an explicit transition_role, it does NOT infer BLOCKING_REQUIREMENT for EQUIPMENT
    default_equip = GuideRule(
        id="RULE_DEFAULT_EQUIP",
        requirement_type=RequirementType.EQUIPMENT,
        observable_via=[ObservabilityMethod.API],
    )
    assert default_equip.transition_role != TransitionRuleRole.BLOCKING_REQUIREMENT
    assert default_equip.transition_role == TransitionRuleRole.ADVISORY


def test_transition_role_decoupling_from_observability_and_provenance() -> None:
    """Verify transition_role is decoupled from observability and provenance."""
    rule1 = GuideRule(
        id="RULE_OBS_DECOUPLED",
        provenance=RuleSourceType.BLUEPRINT_V2,
        observable_via=[ObservabilityMethod.API, ObservabilityMethod.GEAR_AUDIT],
        transition_role=TransitionRuleRole.ADVISORY,
    )
    assert rule1.transition_role == TransitionRuleRole.ADVISORY

    rule2 = GuideRule(
        id="RULE_PROV_DECOUPLED",
        provenance=RuleSourceType.WRITTEN_GUIDE,
        observable_via=[ObservabilityMethod.API],
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
    )
    assert rule2.transition_role == TransitionRuleRole.BLOCKING_REQUIREMENT


def test_evaluable_marked_false_when_unsupported_observation_paths() -> None:
    """Verify rules lacking supported observation paths are marked evaluable=False."""
    # Supported methods: API, GEAR_AUDIT, SKILL_AUDIT, PASSIVE_AUDIT
    for method in SUPPORTED_OBSERVABILITY_METHODS:
        r = GuideRule(
            id=f"RULE_SUP_{method.value}",
            observable_via=[method],
        )
        assert r.evaluable is True

    # Only VISION -> evaluable=False
    r_vision = GuideRule(
        id="RULE_VISION_ONLY",
        observable_via=[ObservabilityMethod.VISION],
    )
    assert r_vision.evaluable is False

    # Only MANUAL -> evaluable=False
    r_manual = GuideRule(
        id="RULE_MANUAL_ONLY",
        observable_via=[ObservabilityMethod.MANUAL],
    )
    assert r_manual.evaluable is False

    # VISION and MANUAL only -> evaluable=False
    r_both = GuideRule(
        id="RULE_VISION_MANUAL",
        observable_via=[ObservabilityMethod.VISION, ObservabilityMethod.MANUAL],
    )
    assert r_both.evaluable is False

    # Empty observable_via -> evaluable=False
    r_empty = GuideRule(
        id="RULE_EMPTY_OBS",
        observable_via=[],
    )
    assert r_empty.evaluable is False

    # Explicit evaluable=True overridden when no supported observation method
    r_forced_true = GuideRule(
        id="RULE_FORCED_TRUE",
        observable_via=[ObservabilityMethod.VISION],
        evaluable=True,
    )
    assert r_forced_true.evaluable is False

    # Mixed with supported method -> evaluable=True
    r_mixed = GuideRule(
        id="RULE_MIXED",
        observable_via=[ObservabilityMethod.VISION, ObservabilityMethod.GEAR_AUDIT],
    )
    assert r_mixed.evaluable is True

    # Explicit evaluable=False with supported method preserves False
    r_explicit_false = GuideRule(
        id="RULE_EXPLICIT_FALSE",
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
        evaluable=False,
    )
    assert r_explicit_false.evaluable is False


def test_trigger_metadata_extraction() -> None:
    """Verify trigger metadata extraction for min_level, max_level, and stage."""
    rule_level = GuideRule(
        id="RULE_LVL",
        trigger={"type": "CHARACTER_LEVEL", "min_level": 52, "max_level": 55},
        observable_via=[ObservabilityMethod.API],
    )
    assert rule_level.min_level == 52
    assert rule_level.max_level == 55

    rule_stage = GuideRule(
        id="RULE_STAGE",
        trigger={"type": "PROGRESSION_STAGE", "stage": "lvl 33-51"},
        observable_via=[ObservabilityMethod.API],
    )
    assert rule_stage.stage == "lvl 33-51"
