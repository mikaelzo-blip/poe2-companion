"""Unit tests for EquippedSlotEntry and EquippedLoadout domain models."""

import pytest
from companion.state.provenance import VerificationState
from companion.equipment.baseline import BaselineSource
from companion.equipment.schema import (
    ItemCandidate,
    SlotConflictTopology,
    SlotOccupancy,
    SlotType,
    WeaponSetContext,
)
from companion.equipment.loadout import (
    EquippedLoadout,
    EquippedSlotEntry,
)


def make_dummy_item(name: str, slot: SlotType) -> ItemCandidate:
    return ItemCandidate(
        item_id=f"id_{name}",
        name=name,
        base_type=name,
        slot=slot,
        slot_occupancy=SlotOccupancy.SINGLE_SLOT,
        slot_conflict_topology=SlotConflictTopology(
            occupied_slots=[slot],
            conflicting_slots=[slot],
            is_known=True,
        ),
    )


def test_loadout_initial_draft_state():
    loadout = EquippedLoadout.create_draft(character_id="char_test")
    assert loadout.is_finalized is False
    assert loadout.revision == 0 or loadout.revision == 1


def test_loadout_set_slot_during_draft_does_not_increment_revision():
    loadout = EquippedLoadout.create_draft(character_id="char_test")
    boots = make_dummy_item("Furtive Boots", SlotType.BOOTS)
    ring1 = make_dummy_item("Gold Ring", SlotType.RING_1)

    loadout.set_slot(SlotType.BOOTS, boots, source=BaselineSource.CLIPBOARD_ITEM_TEXT)
    initial_rev = loadout.revision

    loadout.set_slot(SlotType.RING_1, ring1, source=BaselineSource.CLIPBOARD_ITEM_TEXT)
    assert loadout.revision == initial_rev
    assert loadout.is_finalized is False
    assert loadout.get_slot(SlotType.BOOTS).item.name == "Furtive Boots"
    assert loadout.get_slot(SlotType.RING_1).item.name == "Gold Ring"


def test_loadout_finalize_establishes_revision_1():
    loadout = EquippedLoadout.create_draft(character_id="char_test")
    boots = make_dummy_item("Furtive Boots", SlotType.BOOTS)
    loadout.set_slot(SlotType.BOOTS, boots, source=BaselineSource.CLIPBOARD_ITEM_TEXT)

    loadout.finalize(loadout_id="loadout_alpha")
    assert loadout.is_finalized is True
    assert loadout.loadout_id == "loadout_alpha"
    assert loadout.revision == 1
    assert SlotType.BOOTS in loadout.known_slots
    assert SlotType.HELMET in loadout.unknown_slots


def test_loadout_ring1_and_ring2_independence():
    loadout = EquippedLoadout.create_draft(character_id="char_test")
    ring1 = make_dummy_item("Iron Ring", SlotType.RING_1)
    ring2 = make_dummy_item("Topaz Ring", SlotType.RING_2)

    loadout.set_slot(SlotType.RING_1, ring1, source=BaselineSource.CLIPBOARD_ITEM_TEXT)
    loadout.set_slot(SlotType.RING_2, ring2, source=BaselineSource.CLIPBOARD_ITEM_TEXT)

    assert loadout.get_slot(SlotType.RING_1).item.name == "Iron Ring"
    assert loadout.get_slot(SlotType.RING_2).item.name == "Topaz Ring"


def test_loadout_weapon_sets():
    loadout = EquippedLoadout.create_draft(character_id="char_test")
    staff = make_dummy_item("Chiming Staff", SlotType.MAIN_HAND)
    crossbow = make_dummy_item("Bombard Crossbow", SlotType.MAIN_HAND)

    loadout.set_slot(
        SlotType.MAIN_HAND,
        staff,
        source=BaselineSource.CLIPBOARD_ITEM_TEXT,
        weapon_set=WeaponSetContext.WEAPON_SET_1,
    )
    loadout.set_slot(
        SlotType.MAIN_HAND,
        crossbow,
        source=BaselineSource.CLIPBOARD_ITEM_TEXT,
        weapon_set=WeaponSetContext.WEAPON_SET_2,
    )

    s1_item = loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_1)
    s2_item = loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_2)

    assert s1_item.item.name == "Chiming Staff"
    assert s2_item.item.name == "Bombard Crossbow"
