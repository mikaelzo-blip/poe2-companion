"""Integration tests for the complete Equipment Intelligence pipeline."""

from pathlib import Path
import pytest
from companion.equipment.schema import SlotType
from companion.equipment.baseline_cli import run_baseline_set, run_baseline_show
from companion.equipment.loadout_cli import (
    run_loadout_finalize,
    run_loadout_set_item,
    run_loadout_show,
)
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.loadout_promotion import promote_candidate_to_loadout
from companion.equipment.parser import parse_item_text
from companion.equipment.precedence import Verdict

BOOTS_OLD = """Item Class: Boots
Rarity: Magic
Runner Boots
--------
Evasion Rating: 50
--------
Requirements:
Level: 10
--------
Item Level: 15
--------
+10% to Fire Resistance
"""

BOOTS_NEW = """Item Class: Boots
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


def test_full_equipment_pipeline(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "test_char"

    # Step 1: draft loadout setup
    run_loadout_set_item(runtime_dir, char_id, "boots", BOOTS_OLD)
    loadout = run_loadout_finalize(runtime_dir, char_id)
    assert loadout.revision == 1
    assert loadout.is_finalized is True
    assert SlotType.BOOTS in loadout.known_slots

    # Step 2: baseline set anchored to rev 1
    base = run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=1200,
        fire_res=75,
        fire_raw=85,
        lightning_res=32,
        lightning_raw=32,
        dex=50,
        int=50,
        movement_speed=0,
    )
    assert base.anchored_loadout_revision == 1
    assert base.lightning_deficit == 43

    # Step 3: evaluate candidate boots
    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        candidate_text=BOOTS_NEW,
        character_id=char_id,
    )
    assert rec.slot == SlotType.BOOTS
    assert rec.projection.life.delta == 66.0
    assert rec.projection.lightning_res.delta == 28.0
    assert rec.projection.fire_res.delta == -10.0
    # Overcap buffer absorbs fire loss (85 - 10 = 75 >= 75)
    assert rec.projection.fire_res.projected_absolute == 75
    # Lightning deficit shrinks: 32 + 28 = 60
    assert rec.projection.lightning_res.projected_absolute == 60
    assert rec.verdict == Verdict.EQUIP_NOW

    # Step 4: promote candidate
    cand = parse_item_text(BOOTS_NEW)
    new_loadout, new_base = promote_candidate_to_loadout(
        loadout=loadout,
        candidate=cand,
        slot=SlotType.BOOTS,
        baseline=base,
    )
    assert new_loadout.revision == 2
    assert new_base.anchored_loadout_revision == 2
    assert new_base.raw_lightning_res.value == 60
    assert new_base.raw_fire_res.value == 75
