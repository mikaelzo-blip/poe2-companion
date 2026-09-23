"""FIXTURE-BASED INTEGRATION TESTS Scenario 5: Two-handed staff replaces set-1 MH and OH while set-2 crossbow remains intact."""

from pathlib import Path
import pytest
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.equipment.loadout_cli import (
    load_loadout,
    run_loadout_finalize,
    run_loadout_set_item,
    save_loadout,
)
from companion.equipment.loadout_promotion import promote_candidate_to_loadout
from companion.equipment.parser import parse_item_text
from companion.equipment.weapon_projection import validate_weapon_pairing

WAND_SET1 = """Item Class: Wands
Rarity: Magic
Searing Wand
--------
Requirements:
Level: 30
--------
+15% to Fire Resistance
"""

SHIELD_SET1 = """Item Class: Shields
Rarity: Rare
Aegis Wall
Tower Shield
--------
Requirements:
Level: 40
--------
+25% to Fire Resistance
+50 to maximum Life
"""

CROSSBOW_SET2 = """Item Class: Crossbows
Rarity: Rare
Gloom Piercer
Bombard Crossbow
--------
Requirements:
Level: 50
--------
+20% to Physical Damage
"""

STAFF_CANDIDATE = """Item Class: Two Hand Staves
Rarity: Rare
Solar Spire
Chiming Staff
--------
Requirements:
Level: 55
Str: 70
Int: 70
--------
+2 to Level of all Fire Spell Skill Gems
+10% to Fire Resistance
"""


def test_uat_two_handed_projection_and_set2_isolation(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "fubgun_ignite"

    # Setup set 1: Wand + Shield (+40% fire res total)
    run_loadout_set_item(
        runtime_dir,
        char_id,
        "main_hand",
        WAND_SET1,
        weapon_set_name="weapon_set_1",
    )
    run_loadout_set_item(
        runtime_dir,
        char_id,
        "off_hand",
        SHIELD_SET1,
        weapon_set_name="weapon_set_1",
    )

    # Setup set 2: Crossbow (2H)
    run_loadout_set_item(
        runtime_dir,
        char_id,
        "main_hand",
        CROSSBOW_SET2,
        weapon_set_name="weapon_set_2",
    )

    loadout = run_loadout_finalize(runtime_dir, char_id)
    assert loadout.weapon_set_1["main_hand"] is not None
    assert loadout.weapon_set_1["off_hand"] is not None
    assert loadout.weapon_set_2["main_hand"] is not None
    assert loadout.weapon_set_2["off_hand"] is None

    # Equipping 2H staff into set 1
    staff_cand = parse_item_text(
        STAFF_CANDIDATE,
        target_slot=SlotType.MAIN_HAND,
        target_weapon_set=WeaponSetContext.WEAPON_SET_1,
    )
    new_loadout, _ = promote_candidate_to_loadout(
        loadout=loadout,
        candidate=staff_cand,
        slot=SlotType.MAIN_HAND,
        weapon_set=WeaponSetContext.WEAPON_SET_1,
    )

    # Set 1 now has staff in main_hand, off_hand cleared
    assert new_loadout.weapon_set_1["main_hand"].item.name == "Solar Spire"
    assert new_loadout.weapon_set_1["off_hand"] is None

    # Set 2 crossbow is completely untouched and preserved intact!
    assert new_loadout.weapon_set_2["main_hand"].item.name == "Gloom Piercer"
    assert new_loadout.weapon_set_2["off_hand"] is None

    # Crossbow cannot pair with a quiver
    quiver_cand = parse_item_text(
        "Item Class: Quivers\nRarity: Rare\nTest Quiver\n--------\n"
    )
    is_valid, msg = validate_weapon_pairing(
        new_loadout.weapon_set_2["main_hand"].item, quiver_cand
    )
    assert is_valid is False
    assert "Crossbow cannot pair with quiver" in msg
