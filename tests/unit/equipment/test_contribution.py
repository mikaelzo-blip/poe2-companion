"""Unit tests for ItemContribution layer aggregating character-relevant effects."""

import pytest
from companion.equipment.schema import (
    ItemCandidate,
    ModifierScope,
    NormalizedModifier,
    NormalizedModifierType,
    SlotConflictTopology,
    SlotOccupancy,
    SlotType,
    WeaponSetContext,
)
from companion.equipment.contribution import (
    ItemContribution,
    build_item_contribution,
)


def test_build_item_contribution_aggregates_stats():
    item = ItemCandidate(
        item_id="cand_boots_1",
        name="Loath Trail",
        base_type="Furtive Boots",
        slot=SlotType.BOOTS,
        slot_occupancy=SlotOccupancy.SINGLE_SLOT,
        slot_conflict_topology=SlotConflictTopology(
            occupied_slots=[SlotType.BOOTS],
            conflicting_slots=[SlotType.BOOTS],
            is_known=True,
        ),
        local_evasion=142,
        local_energy_shield=29,
        modifiers=[
            NormalizedModifier(
                modifier_type=NormalizedModifierType.MAXIMUM_LIFE,
                scope=ModifierScope.GLOBAL_CHARACTER_STAT,
                value=66.0,
                raw_text="+66 to maximum Life",
            ),
            NormalizedModifier(
                modifier_type=NormalizedModifierType.LIGHTNING_RESISTANCE,
                scope=ModifierScope.GLOBAL_CHARACTER_STAT,
                value=28.0,
                raw_text="+28% to Lightning Resistance",
            ),
            NormalizedModifier(
                modifier_type=NormalizedModifierType.MOVEMENT_SPEED,
                scope=ModifierScope.GLOBAL_CHARACTER_STAT,
                value=10.0,
                raw_text="+10% increased Movement Speed",
            ),
            NormalizedModifier(
                modifier_type=NormalizedModifierType.STRENGTH,
                scope=ModifierScope.GLOBAL_CHARACTER_STAT,
                value=15.0,
                raw_text="+15 to Strength",
            ),
        ],
    )

    contrib = build_item_contribution(item)
    assert contrib.item_id == "cand_boots_1"
    assert contrib.slot == SlotType.BOOTS
    assert contrib.life_delta == 66.0
    assert contrib.lightning_res_delta == 28.0
    assert contrib.movement_speed_delta == 10.0
    assert contrib.str_delta == 15
    assert contrib.local_evasion == 142
    assert contrib.local_energy_shield == 29
    assert contrib.slot_conflict_topology.occupied_slots == [SlotType.BOOTS]


def test_build_item_contribution_preserves_weapon_set_and_topology():
    item = ItemCandidate(
        item_id="cand_staff_1",
        name="Volcano Pillar",
        base_type="Chiming Staff",
        slot=SlotType.MAIN_HAND,
        slot_occupancy=SlotOccupancy.TWO_HAND,
        slot_conflict_topology=SlotConflictTopology(
            occupied_slots=[SlotType.MAIN_HAND, SlotType.OFF_HAND],
            conflicting_slots=[SlotType.MAIN_HAND, SlotType.OFF_HAND],
            allowed_companion_slots=[],
            is_known=True,
        ),
        modifiers=[
            NormalizedModifier(
                modifier_type=NormalizedModifierType.FLAT_FIRE_DAMAGE_SPELL,
                scope=ModifierScope.BUILD_MECHANIC,
                value=15.0,
                raw_text="Adds 10 to 20 Fire Damage to Spells",
            ),
        ],
        weapon_set=WeaponSetContext.WEAPON_SET_1,
    )

    contrib = build_item_contribution(item, target_weapon_set=WeaponSetContext.WEAPON_SET_1)
    assert contrib.slot_occupancy == SlotOccupancy.TWO_HAND
    assert contrib.target_weapon_set == WeaponSetContext.WEAPON_SET_1
    assert contrib.slot_conflict_topology.occupied_slots == [SlotType.MAIN_HAND, SlotType.OFF_HAND]
    assert len(contrib.build_mechanic_modifiers) == 1
