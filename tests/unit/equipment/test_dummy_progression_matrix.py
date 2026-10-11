"""Requirement and attribute cascade progression tests."""

from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.parser import parse_item_text
from companion.equipment.requirements import (
    GemRequirement,
    validate_requirement_cascades,
)
from companion.equipment.schema import SlotType


def test_dummy_unmet_attribute_requirement_triggers_cascade_failure() -> None:
    loadout = EquippedLoadout(loadout_id="dummy_loadout", character_id="dummy_char", revision=1)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="dummy_char",
        anchored_loadout_revision=1,
        strength=40,
    )
    # Item requires 110 Strength, character only has 40
    item_text = """Item Class: Body Armours
Rarity: Rare
Colossus Plate
Astral Plate
--------
Requirements:
Level: 50
Str: 110
--------
+80 to maximum Life
+35% to Fire Resistance
"""
    candidate = parse_item_text(item_text, target_slot=SlotType.BODY_ARMOUR)
    res = validate_requirement_cascades(
        loadout=loadout,
        candidate=candidate,
        slot=SlotType.BODY_ARMOUR,
        baseline=baseline,
    )
    assert res.is_satisfied is False
    assert any(d.attribute == "str" and d.target_type == "candidate" for d in res.candidate_deficiencies)


def test_dummy_requirement_cascade_fails_when_gem_loses_attributes() -> None:
    loadout = EquippedLoadout(loadout_id="dummy_loadout", character_id="dummy_char", revision=1)
    # Character currently has 60 Strength (25 base + 35 from equipped amulet)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="dummy_char",
        anchored_loadout_revision=1,
        strength=60,
    )
    # Current amulet gives +35 Strength
    current_amulet_text = """Item Class: Amulets
Rarity: Rare
Brawn Choker
Coral Amulet
--------
+35 to Strength
+40 to maximum Life
"""
    current_amulet = parse_item_text(current_amulet_text, target_slot=SlotType.AMULET)
    loadout.set_slot(SlotType.AMULET, current_amulet)

    # Candidate amulet gives NO strength
    candidate_amulet_text = """Item Class: Amulets
Rarity: Rare
Pure Fire Amulet
Coral Amulet
--------
+30% to Fire Resistance
+40 to maximum Life
"""
    candidate = parse_item_text(candidate_amulet_text, target_slot=SlotType.AMULET)

    # Critical gem requires 50 Strength. Replacing amulet drops strength to 60 - 35 = 25 < 50!
    critical_gems = [
        GemRequirement(gem_name="Steelskin", strength=50, is_critical=True)
    ]

    res = validate_requirement_cascades(
        loadout=loadout,
        candidate=candidate,
        slot=SlotType.AMULET,
        baseline=baseline,
        critical_gems=critical_gems,
    )
    assert res.is_satisfied is False
    assert any(d.target_type == "gem" and d.target_name == "Steelskin" for d in res.gem_cascading_deficiencies)
