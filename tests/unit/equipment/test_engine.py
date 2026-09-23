"""Unit tests for the central EquipmentIntelligenceEngine."""

from pathlib import Path
import pytest
from companion.equipment.schema import SlotType
from companion.equipment.loadout_cli import run_loadout_set_item, run_loadout_finalize
from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.precedence import Verdict

BOOTS_OLD = """Item Class: Boots
Rarity: Rare
Old Treads
Furtive Boots
--------
Requirements:
Level: 45
--------
+30 to maximum Life
+10% to Fire Resistance
"""

BOOTS_UPGRADE = """Item Class: Boots
Rarity: Rare
Fleet Steps
Furtive Boots
--------
Requirements:
Level: 45
--------
+70 to maximum Life
+30% to Fire Resistance
+20% increased Movement Speed
"""


def test_engine_evaluates_upgrade(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "test_engine_char"

    # Setup loadout with old boots
    run_loadout_set_item(runtime_dir, char_id, "boots", BOOTS_OLD)
    run_loadout_finalize(runtime_dir, char_id)
    run_baseline_set(
        runtime_dir,
        char_id,
        life=2500,
        fire_res=70,
        fire_raw=70,
        movement_speed=10,
    )

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        item_text=BOOTS_UPGRADE,
        character_id=char_id,
        target_slot="boots",
    )

    assert rec.candidate.name == "Fleet Steps"
    assert rec.verdict == Verdict.EQUIP_NOW
    assert rec.projection.life.delta == 40.0
    assert rec.projection.movement_speed.delta == 20.0
    assert "FLEET STEPS" in rec.formatted_report.upper()
