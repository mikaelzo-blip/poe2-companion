"""Unit tests for requirement cascade scenarios across items and build-critical gems."""

import pytest
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.equipment.parser import parse_item_text
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.requirements import (
    GemRequirement,
    validate_requirement_cascades,
)

RING_INT_OLD = """Item Class: Rings
Rarity: Rare
Old Lapis Ring
Lapis Ring
--------
Requirements:
Level: 40
--------
+30 to Intelligence
"""

RING_INT_NEW = """Item Class: Rings
Rarity: Rare
New Iron Ring
Iron Ring
--------
Requirements:
Level: 40
--------
+50 to maximum Life
"""

SHIELD_STR_OLD = """Item Class: Shields
Rarity: Rare
Old Tower Shield
Tower Shield
--------
Requirements:
Level: 45
--------
+25 to Strength
"""

STAFF_NEW = """Item Class: Two Hand Staves
Rarity: Rare
Volcano Pillar
Chiming Staff
--------
Requirements:
Level: 52
--------
+20% to Fire Resistance
"""


def test_swap_satisfies_item_but_breaks_socketed_gem():
    loadout = EquippedLoadout.create_draft(character_id="char_gem")
    old_ring = parse_item_text(RING_INT_OLD, target_slot=SlotType.RING_1)
    loadout.set_slot(SlotType.RING_1, old_ring)

    # Current Int is 110
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_int",
        character_id="char_gem",
        anchored_loadout_revision=1,
        intelligence=110,
    )

    # Gem requires 95 Int (critical gem)
    critical_gems = [
        GemRequirement(gem_name="Flameblast", level=12, intelligence=95)
    ]

    # Swap ring losing 30 Int -> projected Int = 80 < 95!
    new_ring = parse_item_text(RING_INT_NEW, target_slot=SlotType.RING_1)
    res = validate_requirement_cascades(
        loadout=loadout,
        candidate=new_ring,
        slot=SlotType.RING_1,
        baseline=baseline,
        critical_gems=critical_gems,
    )

    assert res.is_satisfied is False
    assert len(res.gem_cascading_deficiencies) == 1
    assert res.gem_cascading_deficiencies[0].target_name == "Flameblast"
    assert res.gem_cascading_deficiencies[0].attribute == "int"
    assert res.gem_cascading_deficiencies[0].shortfall == 15


def test_displaced_offhand_attribute_loss_breaks_gem():
    loadout = EquippedLoadout.create_draft(character_id="char_offhand_gem")
    shield = parse_item_text(SHIELD_STR_OLD, target_slot=SlotType.OFF_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_1)
    loadout.set_slot(SlotType.OFF_HAND, shield, weapon_set=WeaponSetContext.WEAPON_SET_1)

    # Current Str is 100
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_str",
        character_id="char_offhand_gem",
        anchored_loadout_revision=1,
        strength=100,
    )

    # Steelskin requires 90 Str
    critical_gems = [
        GemRequirement(gem_name="Steelskin", level=10, strength=90)
    ]

    # Equipping 2H staff in set 1 displaces off-hand shield with +25 Str!
    # Projected Str = 100 - 25 = 75 < 90!
    staff = parse_item_text(STAFF_NEW, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_1)
    res = validate_requirement_cascades(
        loadout=loadout,
        candidate=staff,
        slot=SlotType.MAIN_HAND,
        baseline=baseline,
        weapon_set=WeaponSetContext.WEAPON_SET_1,
        critical_gems=critical_gems,
    )

    assert res.is_satisfied is False
    assert len(res.gem_cascading_deficiencies) == 1
    assert res.gem_cascading_deficiencies[0].target_name == "Steelskin"
    assert res.gem_cascading_deficiencies[0].shortfall == 15
