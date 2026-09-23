"""UAT Scenario 1: Boots upgrade with life, res deficit reduction, and movement speed."""

from pathlib import Path
import pytest
from companion.equipment.schema import SlotType
from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.precedence import Verdict

BOOTS_CANDIDATE = """Item Class: Boots
Rarity: Rare
Loath Trail
Furtive Boots
--------
Evasion Rating: 142
Energy Shield: 29
--------
Requirements:
Level: 45
Dex: 42
Int: 42
--------
Sockets: S S
--------
Item Level: 48
--------
+66 to maximum Life
+28% to Lightning Resistance
+10% increased Movement Speed
"""


def test_uat_boots_upgrade_equip_now(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "fubgun_ignite"

    # Setup draft loadout with empty boots or basic boots
    run_loadout_set_item(
        runtime_dir,
        char_id,
        "boots",
        "Item Class: Boots\nRarity: Normal\nRaw Boots\n--------\n",
    )
    run_loadout_finalize(runtime_dir, char_id)

    # Character has 43% Lightning Res deficit (effective 32% vs 75% target)
    run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=1500,
        lightning_res=32,
        lightning_raw=32,
        max_lightning_res=75,
        dex=100,
        int=100,
    )

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(BOOTS_CANDIDATE, character_id=char_id)

    assert rec.slot == SlotType.BOOTS
    assert rec.verdict == Verdict.EQUIP_NOW
    assert rec.projection.life.delta == 66.0
    assert rec.projection.lightning_res.delta == 28.0
    assert rec.projection.movement_speed.delta == 10.0
    assert "EQUIP_NOW" in rec.formatted_report
