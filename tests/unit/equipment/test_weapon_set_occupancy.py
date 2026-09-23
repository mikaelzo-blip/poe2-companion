"""Unit tests for weapon set occupancy, off-hand stat subtraction, and cross-set isolation."""

import pytest
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.equipment.parser import parse_item_text
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.occupancy_contribution import compute_weapon_occupancy_contribution
from companion.equipment.weapon_projection import validate_weapon_pairing

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

SHIELD_TEXT = """Item Class: Shields
Rarity: Rare
Aegis Barrier
Spiked Shield
--------
Armour: 120
Evasion Rating: 120
--------
Requirements:
Level: 45
--------
+50 to maximum Life
+30% to Fire Resistance
+25% to Cold Resistance
"""

WAND_TEXT = """Item Class: Wands
Rarity: Rare
Spire Wand
Opal Wand
--------
Requirements:
Level: 45
--------
+15% to Lightning Resistance
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


def test_equipping_staff_replaces_both_and_subtracts_shield_stats():
    loadout = EquippedLoadout.create_draft(character_id="char_test")
    wand = parse_item_text(WAND_TEXT, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_1)
    shield = parse_item_text(SHIELD_TEXT, target_slot=SlotType.OFF_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_1)
    loadout.set_slot(SlotType.MAIN_HAND, wand, weapon_set=WeaponSetContext.WEAPON_SET_1)
    loadout.set_slot(SlotType.OFF_HAND, shield, weapon_set=WeaponSetContext.WEAPON_SET_1)

    staff = parse_item_text(STAFF_TEXT, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_1)
    occ = compute_weapon_occupancy_contribution(loadout, staff, WeaponSetContext.WEAPON_SET_1)

    # Subtraction checks
    assert occ.displaced_fire_res == 30.0
    assert occ.net_fire_res_delta == -10.0  # 20 staff - 30 shield
    assert occ.displaced_cold_res == 25.0
    assert occ.net_cold_res_delta == -25.0  # 0 staff - 25 shield
    assert occ.displaced_life == 50.0
    assert occ.net_life_delta == -50.0


def test_crossbow_cannot_retain_or_equip_quiver():
    crossbow = parse_item_text(CROSSBOW_TEXT, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_2)
    quiver = parse_item_text(QUIVER_TEXT, target_slot=SlotType.OFF_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_2)

    valid, err = validate_weapon_pairing(crossbow, quiver)
    assert not valid
    assert "quiver" in err.lower()


def test_bow_permits_quiver():
    bow = parse_item_text(BOW_TEXT, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_2)
    quiver = parse_item_text(QUIVER_TEXT, target_slot=SlotType.OFF_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_2)

    valid, err = validate_weapon_pairing(bow, quiver)
    assert valid
    assert err == ""
