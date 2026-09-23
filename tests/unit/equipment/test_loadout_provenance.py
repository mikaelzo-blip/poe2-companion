"""Unit tests for loadout provenance tracking and conflict detection."""

import pytest
from companion.state.provenance import VerificationState
from companion.equipment.baseline import BaselineSource
from companion.equipment.schema import (
    ItemCandidate,
    SlotConflictTopology,
    SlotOccupancy,
    SlotType,
)
from companion.equipment.loadout import EquippedSlotEntry
from companion.equipment.loadout_provenance import detect_loadout_conflict


def make_slot_entry(
    name: str,
    slot: SlotType,
    source: BaselineSource,
    evidence_ref: str,
) -> EquippedSlotEntry:
    item = ItemCandidate(
        item_id=f"id_{name}",
        name=name,
        base_type="Iron Ring",
        slot=slot,
        slot_occupancy=SlotOccupancy.SINGLE_SLOT,
        slot_conflict_topology=SlotConflictTopology(occupied_slots=[slot]),
    )
    return EquippedSlotEntry(
        item=item,
        slot=slot,
        source=source,
        evidence_ref=evidence_ref,
    )


def test_conflict_detection_when_items_differ():
    manual_entry = make_slot_entry(
        name="Manual Ring",
        slot=SlotType.RING_1,
        source=BaselineSource.CLIPBOARD_ITEM_TEXT,
        evidence_ref="manual_hash_1",
    )
    api_entry = make_slot_entry(
        name="Official API Ring",
        slot=SlotType.RING_1,
        source=BaselineSource.GGG_OFFICIAL_API,
        evidence_ref="api_hash_2",
    )

    is_conflict, resolved_entry = detect_loadout_conflict(manual_entry, api_entry)
    assert is_conflict is True
    assert resolved_entry.verification == VerificationState.CONFLICTING
    assert "manual_hash_1" in resolved_entry.evidence_ref
    assert "api_hash_2" in resolved_entry.evidence_ref


def test_corroboration_when_items_match():
    manual_entry = make_slot_entry(
        name="Identical Ring",
        slot=SlotType.RING_1,
        source=BaselineSource.CLIPBOARD_ITEM_TEXT,
        evidence_ref="hash_common",
    )
    api_entry = make_slot_entry(
        name="Identical Ring",
        slot=SlotType.RING_1,
        source=BaselineSource.GGG_OFFICIAL_API,
        evidence_ref="hash_common",
    )

    is_conflict, resolved_entry = detect_loadout_conflict(manual_entry, api_entry)
    assert is_conflict is False
    assert resolved_entry.verification == VerificationState.CORROBORATED
