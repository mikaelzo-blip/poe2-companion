"""Unit tests for PoE2 item text parser and verified slot-conflict topology."""

import pytest
from companion.equipment.schema import (
    SlotType,
    SlotOccupancy,
    NormalizedModifierType,
    WeaponSetContext,
)
from companion.equipment.parser import parse_item_text, parse_slot_topology_for_base

BOOTS_TEXT = """Item Class: Boots
Rarity: Rare
Loath Trail
Furtive Boots
--------
Evasion Rating: 142 (augmented)
Energy Shield: 29 (augmented)
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

STAFF_TEXT = """Item Class: Two Hand Staves
Rarity: Rare
Volcano Pillar
Chiming Staff
--------
Physical Damage: 45-93
--------
Requirements:
Level: 52
Str: 85
Int: 85
--------
Item Level: 55
--------
18% increased Spell Damage (implicit)
--------
+2 to Level of all Fire Spell Skill Gems
72% increased Fire Damage
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
Dex: 112
Str: 40
--------
Item Level: 54
--------
+24% to Physical Damage
"""

QUIVER_TEXT = """Item Class: Quivers
Rarity: Rare
Eagle Flight
Broadhead Arrow Quiver
--------
Requirements:
Level: 45
--------
Item Level: 46
--------
Adds 5 to 10 Physical Damage to Bow Attacks
"""

BOW_TEXT = """Item Class: Bows
Rarity: Rare
Storm Flight
Recurve Bow
--------
Requirements:
Level: 50
Dex: 120
--------
Item Level: 52
--------
+15% to Attack Speed
"""

UNKNOWN_TEXT = """Item Class: Unknown Artifact
Rarity: Unique
The Enigma
Strange Relic
--------
Item Level: 100
--------
+10 to All Attributes
"""


def test_parse_boots():
    item = parse_item_text(BOOTS_TEXT)
    assert item.name == "Loath Trail"
    assert item.base_type == "Furtive Boots"
    assert item.rarity == "rare"
    assert item.slot == SlotType.BOOTS
    assert item.slot_occupancy == SlotOccupancy.SINGLE_SLOT
    assert item.slot_conflict_topology.occupied_slots == [SlotType.BOOTS]
    assert item.slot_conflict_topology.conflicting_slots == [SlotType.BOOTS]
    assert item.slot_conflict_topology.is_known is True
    assert item.local_evasion == 142
    assert item.local_energy_shield == 29
    assert item.required_level == 45
    assert item.required_dex == 42
    assert item.required_int == 42
    assert item.item_level == 48

    mod_types = [m.modifier_type for m in item.modifiers]
    assert NormalizedModifierType.MAXIMUM_LIFE in mod_types
    assert NormalizedModifierType.LIGHTNING_RESISTANCE in mod_types
    assert NormalizedModifierType.MOVEMENT_SPEED in mod_types


def test_parse_two_handed_staff_topology():
    item = parse_item_text(STAFF_TEXT, target_weapon_set=WeaponSetContext.WEAPON_SET_1)
    assert item.name == "Volcano Pillar"
    assert item.base_type == "Chiming Staff"
    assert item.slot == SlotType.MAIN_HAND
    assert item.slot_occupancy == SlotOccupancy.TWO_HAND
    assert item.slot_conflict_topology.occupied_slots == [SlotType.MAIN_HAND, SlotType.OFF_HAND]
    assert item.slot_conflict_topology.conflicting_slots == [SlotType.MAIN_HAND, SlotType.OFF_HAND]
    assert item.slot_conflict_topology.allowed_companion_slots == []
    assert item.slot_conflict_topology.is_known is True
    assert item.weapon_set == WeaponSetContext.WEAPON_SET_1


def test_parse_two_handed_crossbow_topology():
    item = parse_item_text(CROSSBOW_TEXT, target_weapon_set=WeaponSetContext.WEAPON_SET_2)
    assert item.base_type == "Bombard Crossbow"
    assert item.slot == SlotType.MAIN_HAND
    assert item.slot_occupancy == SlotOccupancy.TWO_HAND
    assert item.slot_conflict_topology.occupied_slots == [SlotType.MAIN_HAND, SlotType.OFF_HAND]
    assert item.slot_conflict_topology.conflicting_slots == [SlotType.MAIN_HAND, SlotType.OFF_HAND]
    assert item.slot_conflict_topology.allowed_companion_slots == []
    assert item.weapon_set == WeaponSetContext.WEAPON_SET_2


def test_parse_quiver_topology():
    item = parse_item_text(QUIVER_TEXT)
    assert item.slot == SlotType.OFF_HAND
    assert item.slot_occupancy == SlotOccupancy.OFF_HAND
    assert item.slot_conflict_topology.occupied_slots == [SlotType.OFF_HAND]
    # Quivers cannot pair with crossbows
    assert item.slot_conflict_topology.allowed_companion_slots == []


def test_parse_bow_topology():
    item = parse_item_text(BOW_TEXT)
    assert item.slot == SlotType.MAIN_HAND
    assert item.slot_occupancy == SlotOccupancy.TWO_HAND
    assert item.slot_conflict_topology.occupied_slots == [SlotType.MAIN_HAND, SlotType.OFF_HAND]
    assert item.slot_conflict_topology.allowed_companion_slots == [SlotType.OFF_HAND]


def test_parse_unknown_topology():
    item = parse_item_text(UNKNOWN_TEXT)
    assert item.slot_occupancy == SlotOccupancy.UNKNOWN_OCCUPANCY
    assert item.slot_conflict_topology.is_known is False


def test_parse_single_line_requires():
    raw_text = """Item Class: Boots
Rarity: Unique
The Knight-errant
Mail Sabatons
--------
Armour: 32 (augmented)
Evasion Rating: 25 (augmented)
--------
Requires: Level 6
--------
Item Level: 15
--------
10% increased Movement Speed
"""
    item = parse_item_text(raw_text)
    assert item.required_level == 6
    assert item.required_str == 0
    assert item.required_dex == 0
    assert item.required_int == 0
    assert not any("requires" in m.raw_text.lower() for m in item.modifiers)
    assert not any(m.modifier_type == NormalizedModifierType.UNKNOWN_MODIFIER for m in item.modifiers)


def test_parse_inline_multi_attribute_requirements():
    raw_text = """Item Class: Gloves
Rarity: Rare
Doom Touch
Strapped Mitts
--------
Requires: Level 15, 20 Str, 12 Dex
--------
Item Level: 18
--------
+15 to maximum Life
"""
    item = parse_item_text(raw_text)
    assert item.required_level == 15
    assert item.required_str == 20
    assert item.required_dex == 12
    assert item.required_int == 0
    assert not any("requires" in m.raw_text.lower() for m in item.modifiers)


def test_parse_modifier_annotations_filtered():
    raw_text = """Item Class: Boots
Rarity: Unique
The Knight-errant
Mail Sabatons
--------
Requires: Level 6
--------
{ Unique Modifier — Speed }
10% increased Movement Speed
"""
    item = parse_item_text(raw_text)
    assert len(item.modifiers) == 1
    assert item.modifiers[0].modifier_type == NormalizedModifierType.MOVEMENT_SPEED
    assert "{ Unique Modifier — Speed }" in item.annotations
    assert not any(m.modifier_type == NormalizedModifierType.UNKNOWN_MODIFIER for m in item.modifiers)


def test_parse_unique_flavor_text_separated():
    raw_text = """Item Class: Boots
Rarity: Unique
The Knight-errant
Mail Sabatons
--------
Armour: 32 (augmented)
Evasion Rating: 25 (augmented)
--------
Requires: Level 6
--------
Item Level: 15
--------
{ Unique Modifier — Speed }
10% increased Movement Speed
--------
Some search forever for their path.
"""
    item = parse_item_text(raw_text)
    assert item.flavor_text == "Some search forever for their path."
    assert not any(m.raw_text == "Some search forever for their path." for m in item.modifiers)
    assert not any(m.modifier_type == NormalizedModifierType.UNKNOWN_MODIFIER for m in item.modifiers)


def test_parse_unique_preserves_real_unknown_affix_and_separates_flavor():
    raw_text = """Item Class: Boots
Rarity: Unique
The Knight-errant
Mail Sabatons
--------
Requires: Level 6
--------
{ Unique Modifier — Speed }
10% increased Movement Speed
{ Unique Modifier }
10% increased Light Radius
--------
Some search forever for their path.
"""
    item = parse_item_text(raw_text)
    assert item.flavor_text == "Some search forever for their path."
    unknown_mods = [m for m in item.modifiers if m.modifier_type == NormalizedModifierType.UNKNOWN_MODIFIER]
    assert len(unknown_mods) == 1
    assert unknown_mods[0].raw_text == "10% increased Light Radius"
