"""Unit tests for companion gear loadout CLI commands."""

from pathlib import Path
import pytest
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.loadout_cli import (
    load_loadout,
    save_loadout,
    run_loadout_set_item,
    run_loadout_finalize,
    run_loadout_show,
    run_loadout_clear,
)

BOOTS_TEXT = """Item Class: Boots
Rarity: Rare
Loath Trail
Furtive Boots
--------
Evasion Rating: 142
Energy Shield: 29
--------
Requirements:
Level: 45
--------
+66 to maximum Life
+28% to Lightning Resistance
"""

STAFF_TEXT = """Item Class: Two Hand Staves
Rarity: Rare
Volcano Pillar
Chiming Staff
--------
Physical Damage: 45-93
--------
Requirements:
Level: 52
--------
72% increased Fire Damage
"""


def test_loadout_cli_workflow(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "test_char"

    # 1. Ingest boots via clipboard/text
    loadout = run_loadout_set_item(
        runtime_dir=runtime_dir,
        character_id=char_id,
        slot_name="boots",
        item_text=BOOTS_TEXT,
    )
    assert loadout.is_finalized is False
    assert loadout.revision == 1
    assert loadout.get_slot(SlotType.BOOTS).item.name == "Loath Trail"

    # 2. Ingest staff to weapon_set_1
    loadout = run_loadout_set_item(
        runtime_dir=runtime_dir,
        character_id=char_id,
        slot_name="main_hand",
        weapon_set_name="weapon_set_1",
        item_text=STAFF_TEXT,
    )
    assert loadout.is_finalized is False
    assert loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_1).item.name == "Volcano Pillar"

    # 3. Finalize loadout
    finalized = run_loadout_finalize(
        runtime_dir=runtime_dir,
        character_id=char_id,
        loadout_id="fubgun_v1",
    )
    assert finalized.is_finalized is True
    assert finalized.revision == 1
    assert SlotType.BOOTS in finalized.known_slots
    assert SlotType.HELMET in finalized.unknown_slots

    # 4. Show loadout
    show_output = run_loadout_show(runtime_dir=runtime_dir, character_id=char_id)
    assert "Loath Trail" in show_output
    assert "Volcano Pillar" in show_output
    assert "Revision: 1" in show_output

    # 5. Clear a slot
    cleared = run_loadout_clear(
        runtime_dir=runtime_dir,
        character_id=char_id,
        slot_name="boots",
    )
    assert cleared.get_slot(SlotType.BOOTS) is None
