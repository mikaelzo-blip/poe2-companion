"""Unit tests for Milestone 9 survival advisory rules."""

import pytest
from companion.intelligence.schema import AdvisoryCategory, AdvisorySeverity
from companion.intelligence.survival import evaluate_survival_rules
from companion.vision.schema import CharacterPanelStats


def test_survival_rules_without_stats() -> None:
    advisories = evaluate_survival_rules(panel_stats=None, character_level=50)
    assert len(advisories) == 1
    assert advisories[0].severity == AdvisorySeverity.INFO
    assert "no defensive stats" in advisories[0].description.lower()


def test_survival_rules_uncapped_resists_in_maps() -> None:
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
    assert any(a.code == "RES_UNCAPPED_FIRE" and a.severity == AdvisorySeverity.CRITICAL for a in uncapped)
    assert any(a.code == "RES_UNCAPPED_LIGHTNING" and a.severity == AdvisorySeverity.CRITICAL for a in uncapped)

    chaos = [a for a in advisories if a.code == "CHAOS_RES_LOW"]
    assert len(chaos) == 1
    assert chaos[0].severity == AdvisorySeverity.WARNING


def test_survival_rules_deficient_life_pool() -> None:
    stats = CharacterPanelStats(
        life=1200,  # Expected ~2450 at level 70
        mana=500,
        spirit=100,
        fire_res=75,
        cold_res=75,
        lightning_res=75,
        chaos_res=10,
        armour=1000,
        evasion=1000,
    )
    advisories = evaluate_survival_rules(panel_stats=stats, character_level=70)
    life_adv = [a for a in advisories if a.code == "LIFE_POOL_DEFICIENT"]
    assert len(life_adv) == 1
    assert life_adv[0].severity == AdvisorySeverity.CRITICAL
