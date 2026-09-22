"""Unit tests for Milestone 9 survival advisory rules."""

import pytest
from companion.intelligence.schema import (
    AdvisoryCategory,
    AdvisorySeverity,
    ProvenanceCategory,
)
from companion.intelligence.survival import evaluate_survival_rules
from companion.vision.schema import CharacterPanelStats


def test_survival_rules_without_stats() -> None:
    """Missing stats emit informative advisory with SOURCE_BACKED provenance."""
    advisories = evaluate_survival_rules(panel_stats=None, character_level=50)
    assert len(advisories) == 1
    assert advisories[0].severity == AdvisorySeverity.INFO
    assert advisories[0].is_inference is False
    assert advisories[0].provenance == ProvenanceCategory.SOURCE_BACKED
    assert "no defensive stats" in advisories[0].description.lower()


def test_survival_rules_endgame_75_cap_labeled_inference() -> None:
    """Uncapped elemental resists at endgame evaluate as labeled inference."""
    stats = CharacterPanelStats(
        life=2800,
        mana=600,
        spirit=100,
        fire_res=55,
        cold_res=75,
        lightning_res=40,
        chaos_res=-30,
        armour=3500,
        evasion=1200,
    )
    advisories = evaluate_survival_rules(panel_stats=stats, character_level=70, current_act=7)

    uncapped = [a for a in advisories if a.code.startswith("RES_UNCAPPED_")]
    assert len(uncapped) == 2  # fire and lightning
    for adv in uncapped:
        assert adv.is_inference is True
        assert adv.provenance == ProvenanceCategory.LABELED_INFERENCE

    # Verify pruned heuristics do NOT emit advisories
    assert not any(a.code == "CHAOS_RES_LOW" for a in advisories)
    assert not any(a.code.startswith("LIFE_POOL_") for a in advisories)


def test_survival_rules_heuristics_pruned() -> None:
    """Arbitrary act resistance scaling curve, negative chaos, and life math are pruned."""
    stats = CharacterPanelStats(
        life=500,  # Low life should not trigger fabricated formula
        mana=500,
        spirit=100,
        fire_res=30,  # Under old curve (20 + 2*10 = 40) this would trigger
        cold_res=30,
        lightning_res=30,
        chaos_res=-40,  # Negative chaos should not trigger
        armour=1000,
        evasion=1000,
    )
    # Character in Act 2, level 25 (not endgame)
    advisories = evaluate_survival_rules(panel_stats=stats, character_level=25, current_act=2)
    # No advisories emitted because act scaling curve was removed
    assert len(advisories) == 0
