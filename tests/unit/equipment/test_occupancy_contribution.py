"""Unit tests for OccupancyContribution accounting for displaced weapon set slots."""

import pytest
from companion.equipment.schema import SlotType, SlotOccupancy, WeaponSetContext
from companion.equipment.parser import parse_item_text
from companion.equipment.contribution import build_item_contribution
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.occupancy_contribution import (
    OccupancyContribution,
    compute_weapon_occupancy_contribution,
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


def test_two_handed_staff_displaces_main_and_off_hand():
    loadout = EquippedLoadout.create_draft(character_id="char1")
    wand = parse_item_text(WAND_TEXT, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_1)
    shield = parse_item_text(SHIELD_TEXT, target_slot=SlotType.OFF_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_1)
    loadout.set_slot(SlotType.MAIN_HAND, wand, weapon_set=WeaponSetContext.WEAPON_SET_1)
    loadout.set_slot(SlotType.OFF_HAND, shield, weapon_set=WeaponSetContext.WEAPON_SET_1)

    staff = parse_item_text(STAFF_TEXT, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_1)

    occ = compute_weapon_occupancy_contribution(loadout, staff, WeaponSetContext.WEAPON_SET_1)

    assert occ.target_weapon_set == WeaponSetContext.WEAPON_SET_1
    assert len(occ.displaced_entries) == 2
    # Off-hand shield fire res (+30) and wand lightning res (+15) are in displaced
    assert occ.displaced_fire_res == 30.0
    assert occ.displaced_cold_res == 25.0
    assert occ.displaced_lightning_res == 15.0
    assert occ.displaced_life == 50.0
    # Candidate brings +20 fire res
    assert occ.candidate_fire_res == 20.0
    # Net fire res delta = 20 - 30 = -10
    assert occ.net_fire_res_delta == -10.0
    # Net cold res delta = 0 - 25 = -25
    assert occ.net_cold_res_delta == -25.0
