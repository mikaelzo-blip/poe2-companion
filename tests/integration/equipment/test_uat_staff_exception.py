"""UAT Scenario 4: Flameblast staff with fire spell damage is NOT rejected under staff exception."""

from pathlib import Path
import pytest
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.rules import BuildBreakerCertainty, BuildProgressionStage
from companion.equipment.precedence import Verdict

STAFF_CANDIDATE = """Item Class: Two Hand Staves
Rarity: Rare
Volcano Pillar
Chiming Staff
--------
Requirements:
Level: 55
Str: 70
Int: 70
--------
Item Level: 60
--------
+2 to Level of all Fire Spell Skill Gems
72% increased Fire Damage
Adds 15 to 30 Fire Damage to Spells
"""


def test_uat_staff_fire_exception(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "fubgun_ignite"

    # Setup basic 2H staff in set 1
    run_loadout_set_item(
        runtime_dir,
        char_id,
        "main_hand",
        "Item Class: Two Hand Staves\nRarity: Normal\nWood Staff\n--------\n",
        weapon_set_name="set_1",
    )
    run_loadout_finalize(runtime_dir, char_id)

    run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=2500,
        str=100,
        int=100,
    )

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        STAFF_CANDIDATE,
        target_slot="main_hand",
        weapon_set=WeaponSetContext.WEAPON_SET_1,
        character_id=char_id,
        stage=BuildProgressionStage.EARLY_ENDGAME,
    )

    assert rec.slot == SlotType.MAIN_HAND
    # Staff in weapon set 1 is explicitly exempt from the Oil Grenade rule!
    assert rec.safety_eval.certainty == BuildBreakerCertainty.VERIFIED_SAFE
    assert rec.verdict != Verdict.REJECT
    assert "BUILD_BREAKER" not in rec.flags
