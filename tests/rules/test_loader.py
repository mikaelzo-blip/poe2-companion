"""Unit tests for YAML guide rules loader and frozen fixture verification."""

from pathlib import Path
import pytest
import yaml

from companion.rules.loader import DEFAULT_GUIDE_RULES_PATH, load_guide_rules
from companion.rules.schema import (
    GuideRule,
    ObservabilityMethod,
    RequirementType,
    RuleSourceType,
    SourceVerificationStatus,
    TransitionRuleRole,
)


def test_load_guide_rules_default_frozen_fixture() -> None:
    """Verify loading the frozen data/source/guide_rules.yaml fixture."""
    assert DEFAULT_GUIDE_RULES_PATH.is_file()

    rules = load_guide_rules()
    assert len(rules) >= 4

    rules_by_id = {r.id: r for r in rules}
    assert "SWAP_LVL_52" in rules_by_id
    assert "GEM_CAST_ON_DODGE" in rules_by_id
    assert "FUBGUN_WRITTEN_GUIDE_GEAR_PRIORITIES" in rules_by_id
    assert "FUBGUN_WRITTEN_GUIDE_FLASK_SETUP" in rules_by_id


def test_swap_lvl_52_rule_attributes() -> None:
    """Verify SWAP_LVL_52 rule schema, status, role, and evaluability."""
    rules_by_id = {r.id: r for r in load_guide_rules()}
    rule = rules_by_id["SWAP_LVL_52"]

    assert rule.source_status == SourceVerificationStatus.USABLE
    assert rule.status == SourceVerificationStatus.USABLE
    assert rule.transition_role == TransitionRuleRole.COMPLETION_EVIDENCE
    assert rule.requirement_type == RequirementType.EQUIPMENT
    assert rule.evaluable is True
    assert rule.min_level == 52
    assert ObservabilityMethod.API in rule.observable_via
    assert ObservabilityMethod.GEAR_AUDIT in rule.observable_via


def test_gem_cast_on_dodge_rule_attributes() -> None:
    """Verify GEM_CAST_ON_DODGE rule schema, status, role, and evaluability."""
    rules_by_id = {r.id: r for r in load_guide_rules()}
    rule = rules_by_id["GEM_CAST_ON_DODGE"]

    assert rule.source_status == SourceVerificationStatus.USABLE
    assert rule.status == SourceVerificationStatus.USABLE
    assert rule.transition_role == TransitionRuleRole.BLOCKING_REQUIREMENT
    assert rule.requirement_type == RequirementType.SKILL
    assert rule.evaluable is True
    assert rule.min_level == 58
    assert ObservabilityMethod.API in rule.observable_via
    assert ObservabilityMethod.SKILL_AUDIT in rule.observable_via


def test_pending_source_verification_rules_never_promoted() -> None:
    """Verify written guide rules strictly maintain PENDING_SOURCE_VERIFICATION."""
    rules_by_id = {r.id: r for r in load_guide_rules()}

    gear_rule = rules_by_id["FUBGUN_WRITTEN_GUIDE_GEAR_PRIORITIES"]
    assert gear_rule.source_status == SourceVerificationStatus.PENDING_SOURCE_VERIFICATION
    assert gear_rule.transition_role == TransitionRuleRole.PREPARATION
    assert gear_rule.requirement_type == RequirementType.EQUIPMENT
    assert gear_rule.evaluable is True

    flask_rule = rules_by_id["FUBGUN_WRITTEN_GUIDE_FLASK_SETUP"]
    assert flask_rule.source_status == SourceVerificationStatus.PENDING_SOURCE_VERIFICATION
    assert flask_rule.transition_role == TransitionRuleRole.ADVISORY
    assert flask_rule.requirement_type == RequirementType.FLASK
    # Only manual observation -> evaluable MUST be False
    assert flask_rule.observable_via == [ObservabilityMethod.MANUAL]
    assert flask_rule.evaluable is False


def test_loader_marks_inevaluable_rules(tmp_path: Path) -> None:
    """Verify loader forces evaluable=False for rules lacking supported observation methods."""
    yaml_content = {
        "version": "1.0",
        "rules": [
            {
                "id": "RULE_MANUAL_ONLY",
                "name": "Manual Only Rule",
                "status": "USABLE",
                "requirement_type": "EQUIPMENT",
                "transition_role": "ADVISORY",
                "observable_via": ["MANUAL"],
                "evaluable": True,  # should be overridden to False
            },
            {
                "id": "RULE_VISION_ONLY",
                "name": "Vision Only Rule",
                "status": "USABLE",
                "requirement_type": "SKILL",
                "transition_role": "BLOCKING_REQUIREMENT",
                "observable_via": ["VISION"],
            },
            {
                "id": "RULE_NO_OBS",
                "name": "No Obs Rule",
                "status": "USABLE",
                "requirement_type": "PASSIVE",
                "transition_role": "PREPARATION",
                "observable_via": [],
            },
            {
                "id": "RULE_SUPPORTED_OBS",
                "name": "Supported Obs Rule",
                "status": "USABLE",
                "requirement_type": "EQUIPMENT",
                "transition_role": "BLOCKING_REQUIREMENT",
                "observable_via": ["GEAR_AUDIT"],
            },
        ],
    }

    test_file = tmp_path / "test_rules.yaml"
    test_file.write_text(yaml.dump(yaml_content), encoding="utf-8")

    loaded = load_guide_rules(test_file)
    assert len(loaded) == 4

    loaded_by_id = {r.id: r for r in loaded}
    assert loaded_by_id["RULE_MANUAL_ONLY"].evaluable is False
    assert loaded_by_id["RULE_VISION_ONLY"].evaluable is False
    assert loaded_by_id["RULE_NO_OBS"].evaluable is False
    assert loaded_by_id["RULE_SUPPORTED_OBS"].evaluable is True


def test_loader_missing_file_raises_not_found(tmp_path: Path) -> None:
    """Verify loading from a non-existent path raises FileNotFoundError."""
    missing_file = tmp_path / "non_existent_rules.yaml"
    with pytest.raises(FileNotFoundError):
        load_guide_rules(missing_file)


def test_loader_invalid_yaml_structure_raises_error(tmp_path: Path) -> None:
    """Verify loading malformed YAML or non-dict/non-list raises ValueError."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("just a string", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid rules format"):
        load_guide_rules(bad_yaml)
