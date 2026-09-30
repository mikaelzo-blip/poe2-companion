"""Unit tests for equipment intelligence domain schema and models."""

import pytest
from companion.state.provenance import VerificationState
from companion.equipment.schema import (
    SlotType,
    SlotOccupancy,
    SlotConflictTopology,
    ModifierScope,
    NormalizedModifierType,
    NormalizedModifier,
    ItemCandidate,
    WeaponSetContext,
)


def test_slot_type_members():
    assert SlotType.HELMET.value == "helmet"
    assert SlotType.BODY_ARMOUR.value == "body_armour"
    assert SlotType.GLOVES.value == "gloves"
    assert SlotType.BOOTS.value == "boots"
    assert SlotType.AMULET.value == "amulet"
    assert SlotType.RING_1.value == "ring1"
    assert SlotType.RING_2.value == "ring2"
    assert SlotType.BELT.value == "belt"
    assert SlotType.MAIN_HAND.value == "main_hand"
    assert SlotType.OFF_HAND.value == "off_hand"


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Weapon 1", SlotType.MAIN_HAND),
        ("weapon1", SlotType.MAIN_HAND),
        ("weapon_1", SlotType.MAIN_HAND),
        ("Weapon 2", SlotType.OFF_HAND),
        ("weapon2", SlotType.OFF_HAND),
        ("weapon_2", SlotType.OFF_HAND),
    ],
)
def test_weapon_slot_aliases_route_to_the_correct_hand(label, expected):
    assert SlotType.from_str(label) == expected


def test_slot_occupancy_members():
    assert SlotOccupancy.SINGLE_SLOT == "SINGLE_SLOT"
    assert SlotOccupancy.MAIN_HAND == "MAIN_HAND"
    assert SlotOccupancy.OFF_HAND == "OFF_HAND"
    assert SlotOccupancy.TWO_HAND == "TWO_HAND"
    assert SlotOccupancy.SHARED_EQUIPMENT_SLOT == "SHARED_EQUIPMENT_SLOT"
    assert SlotOccupancy.UNKNOWN_OCCUPANCY == "UNKNOWN_OCCUPANCY"


def test_slot_conflict_topology_defaults():
    topology = SlotConflictTopology(occupied_slots=[SlotType.MAIN_HAND, SlotType.OFF_HAND])
    assert topology.occupied_slots == [SlotType.MAIN_HAND, SlotType.OFF_HAND]
    assert topology.conflicting_slots == []
    assert topology.allowed_companion_slots == []
    assert topology.is_known is True


def test_modifier_scope_members():
    assert ModifierScope.LOCAL_ITEM_STAT == "LOCAL_ITEM_STAT"
    assert ModifierScope.GLOBAL_CHARACTER_STAT == "GLOBAL_CHARACTER_STAT"
    assert ModifierScope.REQUIREMENT == "REQUIREMENT"
    assert ModifierScope.BUILD_MECHANIC == "BUILD_MECHANIC"
    assert ModifierScope.CONDITIONAL == "CONDITIONAL"
    assert ModifierScope.UNKNOWN_SCOPE == "UNKNOWN_SCOPE"


def test_normalized_modifier_type_members():
    assert NormalizedModifierType.MAXIMUM_LIFE == "MAXIMUM_LIFE"
    assert NormalizedModifierType.FIRE_RESISTANCE == "FIRE_RESISTANCE"
    assert NormalizedModifierType.COLD_RESISTANCE == "COLD_RESISTANCE"
    assert NormalizedModifierType.LIGHTNING_RESISTANCE == "LIGHTNING_RESISTANCE"
    assert NormalizedModifierType.CHAOS_RESISTANCE == "CHAOS_RESISTANCE"
    assert NormalizedModifierType.LOCAL_ARMOUR == "LOCAL_ARMOUR"
    assert NormalizedModifierType.LOCAL_EVASION == "LOCAL_EVASION"
    assert NormalizedModifierType.LOCAL_ENERGY_SHIELD == "LOCAL_ENERGY_SHIELD"
    assert NormalizedModifierType.LOCAL_ARMOUR_AND_EVASION == "LOCAL_ARMOUR_AND_EVASION"
    assert NormalizedModifierType.MOVEMENT_SPEED == "MOVEMENT_SPEED"
    assert NormalizedModifierType.STRENGTH == "STRENGTH"
    assert NormalizedModifierType.DEXTERITY == "DEXTERITY"
    assert NormalizedModifierType.INTELLIGENCE == "INTELLIGENCE"
    assert NormalizedModifierType.FLAT_FIRE_DAMAGE_ATTACK == "FLAT_FIRE_DAMAGE_ATTACK"
    assert NormalizedModifierType.FLAT_FIRE_DAMAGE_SPELL == "FLAT_FIRE_DAMAGE_SPELL"
    assert NormalizedModifierType.EXTRA_FIRE_DAMAGE == "EXTRA_FIRE_DAMAGE"
    assert NormalizedModifierType.INCREASED_FIRE_DAMAGE == "INCREASED_FIRE_DAMAGE"
    assert NormalizedModifierType.FIRE_SPELL_LEVEL == "FIRE_SPELL_LEVEL"
    assert NormalizedModifierType.ALL_SPELL_LEVEL == "ALL_SPELL_LEVEL"
    assert NormalizedModifierType.SPECIAL_MECHANIC == "SPECIAL_MECHANIC"
    assert NormalizedModifierType.UNKNOWN_MODIFIER == "UNKNOWN_MODIFIER"


def test_normalized_modifier_instantiation():
    mod = NormalizedModifier(
        modifier_type=NormalizedModifierType.FIRE_RESISTANCE,
        scope=ModifierScope.GLOBAL_CHARACTER_STAT,
        value=35.0,
        raw_text="+35% to Fire Resistance",
        is_implicit=False,
        verification_state=VerificationState.VERIFIED,
    )
    assert mod.modifier_type == NormalizedModifierType.FIRE_RESISTANCE
    assert mod.scope == ModifierScope.GLOBAL_CHARACTER_STAT
    assert mod.value == 35.0
    assert mod.is_implicit is False


def test_item_candidate_model():
    item = ItemCandidate(
        item_id="item-boots-001",
        name="Storm Stride",
        base_type="Iron Greaves",
        slot=SlotType.BOOTS,
        slot_occupancy=SlotOccupancy.SINGLE_SLOT,
        slot_conflict_topology=SlotConflictTopology(
            occupied_slots=[SlotType.BOOTS],
            conflicting_slots=[SlotType.BOOTS],
        ),
        rarity="rare",
        item_level=45,
        required_level=32,
        required_str=50,
        local_armour=120,
        raw_text="Item Class: Boots\nRarity: Rare\nStorm Stride\nIron Greaves",
        modifiers=[
            NormalizedModifier(
                modifier_type=NormalizedModifierType.MOVEMENT_SPEED,
                scope=ModifierScope.GLOBAL_CHARACTER_STAT,
                value=20.0,
                raw_text="+20% increased Movement Speed",
            )
        ],
    )
    assert item.item_id == "item-boots-001"
    assert item.slot == SlotType.BOOTS
    assert item.required_str == 50
    assert item.local_armour == 120
    assert len(item.modifiers) == 1


def test_public_verdict_contract_exact_members():
    from companion.equipment.precedence import Verdict

    expected_members = {
        "EQUIP_NOW",
        "CONDITIONAL_UPGRADE",
        "KEEP_FOR_LATER",
        "REJECT",
        "INSUFFICIENT_DATA",
    }
    actual_members = {v.value for v in Verdict}
    assert actual_members == expected_members
    assert "SIDEGRADE" not in actual_members
    assert "STASH_FOR_LATER" not in actual_members
