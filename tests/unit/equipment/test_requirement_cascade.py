"""Unit tests for requirement cascade validation across full loadout and gems."""

import pytest
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.equipment.parser import parse_item_text
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.requirements import (
    GemRequirement,
    RequirementDeficiency,
    RequirementCascadeResult,
    validate_requirement_cascades,
)

AMULET_OLD = """Item Class: Amulets
Rarity: Rare
Jade Amulet
Jade Amulet
--------
Requirements:
Level: 40
--------
+35 to Dexterity
"""

AMULET_NEW = """Item Class: Amulets
Rarity: Rare
Paua Amulet
Paua Amulet
--------
Requirements:
Level: 40
--------
+30 to maximum Life
+20% to Fire Resistance
"""

BOW_TEXT = """Item Class: Bows
Rarity: Rare
Death Bow
Composite Bow
--------
Requirements:
Level: 50
Dex: 120
--------
Physical Damage: 40-80
"""


def test_removing_dex_amulet_breaks_equipped_bow():
    loadout = EquippedLoadout.create_draft(character_id="char_req")
    amulet = parse_item_text(AMULET_OLD, target_slot=SlotType.AMULET)
    bow = parse_item_text(BOW_TEXT, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_2)
    loadout.set_slot(SlotType.AMULET, amulet)
    loadout.set_slot(SlotType.MAIN_HAND, bow, weapon_set=WeaponSetContext.WEAPON_SET_2)

    # Current Dex is 130 (bow requires 120, satisfies with 10 buffer)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_req",
        character_id="char_req",
        anchored_loadout_revision=1,
        dexterity=130,
    )

    # Candidate amulet has 0 Dex (net Dex delta = -35)
    # Projected Dex becomes 95. Bow requires 120 -> shortfall of 25!
    new_amulet = parse_item_text(AMULET_NEW, target_slot=SlotType.AMULET)
    res = validate_requirement_cascades(
        loadout=loadout,
        candidate=new_amulet,
        slot=SlotType.AMULET,
        baseline=baseline,
    )

    assert res.is_satisfied is False
    assert len(res.loadout_cascading_deficiencies) == 1
    deficiency = res.loadout_cascading_deficiencies[0]
    assert deficiency.target_name == "Death Bow"
    assert deficiency.attribute == "dex"
    assert deficiency.shortfall == 25
    assert res.verdict_downgrade in ("CONDITIONAL_UPGRADE", "REJECT")
