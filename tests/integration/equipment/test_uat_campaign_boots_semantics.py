"""Integration tests for campaign boots semantics, resistance priorities, and regressions."""

from pathlib import Path
import pytest
from companion.equipment.schema import SlotType
from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.precedence import Verdict
from companion.equipment.rules import BuildProgressionStage

FUBGUN_BOOTS_WITH_RES = """Item Class: Boots
Rarity: Rare
Storm Stride
Furtive Boots
--------
Requirements:
Level: 25
Dex: 28
Int: 28
--------
+66 to maximum Life
+20% to Lightning Resistance
+10% increased Movement Speed
"""

CAMPAIGN_BOOTS_NO_RES = """Item Class: Boots
Rarity: Rare
Fleet Stride
Furtive Boots
--------
Requirements:
Level: 25
Dex: 28
Int: 28
--------
+70 to maximum Life
+25% increased Movement Speed
"""

BOOTS_WITH_RES_LOSS = """Item Class: Boots
Rarity: Rare
Tradeoff Greaves
Iron Greaves
--------
Requirements:
Level: 25
Str: 30
--------
+70 to maximum Life
+10% increased Movement Speed
"""

EQUIPPED_BOOTS_WITH_RES = """Item Class: Boots
Rarity: Magic
Old Greaves
Iron Greaves
--------
+15% to Lightning Resistance
"""

EQUIPPED_CAPPED_BOOTS = """Item Class: Boots
Rarity: Rare
Guardian Greaves
Iron Greaves
--------
+30% to Lightning Resistance
"""


def test_fubgun_leveling_boots_improves_low_res_equip_now(tmp_path: Path):
    """Section 6: Fubgun Leveling Boots UAT.

    Character has Lightning effective 7 (far below 75). Candidate has Life, MS, +20 Lightning.
    Must evaluate to EQUIP_NOW without being blocked by 75 cap.
    """
    runtime_dir = tmp_path / "runtime"
    char_id = "fubgun_lvl25"

    run_loadout_set_item(
        runtime_dir,
        char_id,
        "boots",
        "Item Class: Boots\nRarity: Normal\nRough Boots\n--------\n",
    )
    run_loadout_finalize(runtime_dir, char_id)

    run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=800,
        lightning_res=7,
        lightning_raw=7,
        fire_res=20,
        fire_raw=20,
        cold_res=15,
        cold_raw=15,
        max_lightning_res=75,
        max_fire_res=75,
        max_cold_res=75,
        dex=50,
        int=50,
        movement_speed=0,
    )

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        FUBGUN_BOOTS_WITH_RES,
        character_id=char_id,
        stage="lvl 15-32",
    )

    assert rec.slot == SlotType.BOOTS
    assert rec.verdict == Verdict.EQUIP_NOW
    assert rec.contextual_analysis.has_unchanged_critical_deficiency is False
    assert rec.contextual_analysis.has_critical_deficiency is False
    assert "GEAR RESISTANCE PRIORITIES (REFERENCE ONLY)" in rec.formatted_report
    assert "None identified." in rec.formatted_report  # Under critical deficiencies


def test_campaign_boots_upgrade_without_resistance_equip_now(tmp_path: Path):
    """Section 14: Campaign boots realistic upgrade without resistance.

    Candidate gives +70 Life, +25 MS, 0 resistance on a character with 7% Lightning.
    Must evaluate to EQUIP_NOW because campaign stage does not require 75 cap on boots.
    """
    runtime_dir = tmp_path / "runtime"
    char_id = "fubgun_no_res_boots"

    run_loadout_set_item(
        runtime_dir,
        char_id,
        "boots",
        "Item Class: Boots\nRarity: Normal\nWhite Boots\n--------\n",
    )
    run_loadout_finalize(runtime_dir, char_id)

    run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=800,
        lightning_res=7,
        fire_res=20,
        cold_res=15,
        dex=50,
        int=50,
        movement_speed=0,
    )

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        CAMPAIGN_BOOTS_NO_RES,
        character_id=char_id,
        stage="lvl 15-32",
    )

    assert rec.slot == SlotType.BOOTS
    assert rec.verdict == Verdict.EQUIP_NOW
    assert rec.contextual_analysis.has_unchanged_critical_deficiency is False
    assert rec.contextual_analysis.has_unresolved_resistance_priority is True
    # Actionable guidance indicates unresolved campaign resistance priorities
    assert any("unresolved campaign resistance priorities" in g.lower() for g in rec.actionable_guidance)


def test_campaign_boots_regression_still_matters_conditional_upgrade(tmp_path: Path):
    """Section 7: Resistance regression still matters.

    Equipped boots give +15% Lightning. Candidate gives 0% Lightning (loses 15%, dropping from 20 to 5).
    Must evaluate to CONDITIONAL_UPGRADE with WORSENS_DEFICIENCY.
    """
    runtime_dir = tmp_path / "runtime"
    char_id = "fubgun_res_loss"

    run_loadout_set_item(
        runtime_dir,
        char_id,
        "boots",
        EQUIPPED_BOOTS_WITH_RES,
    )
    run_loadout_finalize(runtime_dir, char_id)

    run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=800,
        lightning_res=20,
        lightning_raw=20,
        fire_res=20,
        cold_res=15,
        str=50,
        movement_speed=0,
    )

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        BOOTS_WITH_RES_LOSS,
        character_id=char_id,
        stage="lvl 15-32",
    )

    assert rec.slot == SlotType.BOOTS
    assert rec.verdict in (Verdict.CONDITIONAL_UPGRADE, Verdict.KEEP_FOR_LATER)
    assert rec.contextual_analysis.has_worsened_deficiency is True
    assert "WORSENS_DEFICIENCY" in rec.flags


def test_healthy_to_unhealthy_regression_creates_deficiency(tmp_path: Path):
    """Section 8: Healthy-to-unhealthy regression.

    Equipped boots give +30% Lightning on a character at 75% Lightning.
    Candidate gives 0% Lightning (dropping character from 75 to 45).
    Must classify as CREATES_NEW_DEFICIENCY and yield CONDITIONAL_UPGRADE.
    """
    runtime_dir = tmp_path / "runtime"
    char_id = "fubgun_healthy_loss"

    run_loadout_set_item(
        runtime_dir,
        char_id,
        "boots",
        EQUIPPED_CAPPED_BOOTS,
    )
    run_loadout_finalize(runtime_dir, char_id)

    run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=1500,
        lightning_res=75,
        lightning_raw=75,
        max_lightning_res=75,
        str=50,
        movement_speed=0,
    )

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        BOOTS_WITH_RES_LOSS,
        character_id=char_id,
        stage="lvl 15-32",
    )

    assert rec.slot == SlotType.BOOTS
    assert rec.verdict in (Verdict.CONDITIONAL_UPGRADE, Verdict.KEEP_FOR_LATER)
    assert rec.contextual_analysis.has_created_deficiency is True
    assert "CREATES_DEFICIENCY" in rec.flags
