"""Unit tests for stage propagation in engine and recommendation report formatting."""

from pathlib import Path
import pytest
from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.precedence import Verdict
from companion.equipment.rules import BuildProgressionStage

CAMPAIGN_BOOTS = """Item Class: Boots
Rarity: Rare
Gale Track
Wrapped Boots
--------
Evasion Rating: 45
Energy Shield: 12
--------
Requirements:
Level: 22
Dex: 20
Int: 20
--------
Sockets: S S
--------
Item Level: 25
--------
+70 to maximum Life
+25% increased Movement Speed
"""


def test_engine_stage_propagation_campaign_permits_equip_now(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "test_char"

    # Setup basic equipped boots
    run_loadout_set_item(
        runtime_dir,
        char_id,
        "boots",
        "Item Class: Boots\nRarity: Normal\nRaw Boots\n--------\n",
    )
    run_loadout_finalize(runtime_dir, char_id)

    # Character baseline with low campaign resistances (below 75% cap)
    run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=300,
        fire_res=15,
        fire_raw=15,
        cold_res=0,
        cold_raw=0,
        lightning_res=7,
        lightning_raw=7,
        chaos_res=0,
        dex=50,
        int=50,
        str=50,
        movement_speed=0,
        )

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    # Evaluate with stage="lvl 15-32"
    rec = engine.evaluate_candidate(
        item_text=CAMPAIGN_BOOTS,
        character_id=char_id,
        stage="lvl 15-32",
    )

    # Should receive EQUIP_NOW, NOT CONDITIONAL_UPGRADE
    assert rec.verdict == Verdict.EQUIP_NOW
    assert "UNCHANGED_CRITICAL_DEFICIT" not in rec.flags

    # Report should format gear resistance priorities as reference only
    report = rec.formatted_report
    assert "GEAR RESISTANCE PRIORITIES (REFERENCE ONLY)" in report
    assert "Reference cap: 75%" in report
    assert "LOW / HIGH GEAR PRIORITY" in report
    assert "CRITICAL DEFICIENCIES" in report
    # Under critical deficiencies, resistances should not appear
    crit_section = report.split("--- CRITICAL DEFICIENCIES ---")[1].split("---")[0]
    assert "None identified." in crit_section
