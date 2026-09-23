"""Unit tests for cascade deficiency reporting and verdict downgrading."""

import pytest
from companion.equipment.schema import SlotType
from companion.equipment.requirements import (
    RequirementDeficiency,
    RequirementCascadeResult,
    generate_cascade_report,
)


def test_cascade_reporting_and_downgrade():
    deficiency = RequirementDeficiency(
        target_type="equipped_item",
        target_name="Death Bow",
        slot=SlotType.MAIN_HAND,
        attribute="dex",
        required_value=120,
        projected_value=95,
        shortfall=25,
    )
    result = RequirementCascadeResult(
        is_satisfied=False,
        candidate_deficiencies=[],
        loadout_cascading_deficiencies=[deficiency],
        gem_cascading_deficiencies=[],
        verdict_downgrade="CONDITIONAL_UPGRADE",
    )

    report = generate_cascade_report(result)
    assert "REQUIREMENT DEFICIENCY" in report
    assert "Death Bow" in report
    assert "Dex" in report
    assert "Shortfall: 25" in report
    assert "CONDITIONAL_UPGRADE" in report
