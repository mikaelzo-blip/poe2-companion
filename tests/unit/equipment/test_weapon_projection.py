"""Unit tests for weapon set projection and topology validation."""

import pytest
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.equipment.parser import parse_item_text
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.weapon_projection import (
    validate_weapon_pairing,
    project_weapon_set_swap,
)

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
+20% to Fire Resistance
"""

CROSSBOW_TEXT = """Item Class: Crossbows
Rarity: Rare
Gloom Piercer
Bombard Crossbow
--------
Physical Damage: 30-75
--------
Requirements:
Level: 52
--------
+15% to Attack Speed
"""

BOW_TEXT = """Item Class: Bows
Rarity: Rare
Wind Bow
Short Bow
--------
Requirements:
Level: 30
--------
+10 to Dexterity
"""

QUIVER_TEXT = """Item Class: Quivers
Rarity: Rare
Eagle Flight
Broadhead Arrow Quiver
--------
Requirements:
Level: 45
--------
Adds 5 to 10 Physical Damage to Bow Attacks
"""

SHIELD_TEXT = """Item Class: Shields
Rarity: Rare
Aegis Barrier
Spiked Shield
--------
Requirements:
Level: 45
--------
+30% to Fire Resistance
"""


def test_crossbow_cannot_pair_with_quiver():
    crossbow = parse_item_text(CROSSBOW_TEXT, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_2)
    quiver = parse_item_text(QUIVER_TEXT, target_slot=SlotType.OFF_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_2)

    is_valid, reason = validate_weapon_pairing(main_hand=crossbow, off_hand=quiver)
    assert is_valid is False
    assert "Crossbow cannot pair with quiver" in reason or "quiver" in reason.lower()


def test_bow_can_pair_with_quiver():
    bow = parse_item_text(BOW_TEXT, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_2)
    quiver = parse_item_text(QUIVER_TEXT, target_slot=SlotType.OFF_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_2)

    is_valid, reason = validate_weapon_pairing(main_hand=bow, off_hand=quiver)
    assert is_valid is True
    assert reason == ""


def test_staff_occupies_both_slots_leaving_no_companion():
    staff = parse_item_text(STAFF_TEXT, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_1)
    shield = parse_item_text(SHIELD_TEXT, target_slot=SlotType.OFF_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_1)

    is_valid, reason = validate_weapon_pairing(main_hand=staff, off_hand=shield)
    assert is_valid is False


def test_weapon_set_independence():
    loadout = EquippedLoadout.create_draft(character_id="char_indep")
    staff = parse_item_text(STAFF_TEXT, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_1)
    crossbow = parse_item_text(CROSSBOW_TEXT, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_2)

    loadout.set_slot(SlotType.MAIN_HAND, staff, weapon_set=WeaponSetContext.WEAPON_SET_1)
    loadout.set_slot(SlotType.MAIN_HAND, crossbow, weapon_set=WeaponSetContext.WEAPON_SET_2)

    # Projecting a new staff in set 1 does not alter set 2
    new_staff = parse_item_text(STAFF_TEXT, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_1)
    projected = project_weapon_set_swap(loadout, new_staff, target_set=WeaponSetContext.WEAPON_SET_1)

    assert projected.weapon_set_2[SlotType.MAIN_HAND.value].item.name == "Gloom Piercer"
