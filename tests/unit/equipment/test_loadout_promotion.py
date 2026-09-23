"""Unit tests for candidate promotion to equipped loadout."""

import pytest
from companion.state.provenance import VerificationState
from companion.equipment.baseline import (
    BaselineSource,
    CharacterStatBaseline,
)
from companion.equipment.schema import (
    ItemCandidate,
    ModifierScope,
    NormalizedModifier,
    NormalizedModifierType,
    SlotConflictTopology,
    SlotOccupancy,
    SlotType,
)
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.loadout_promotion import promote_candidate_to_loadout


def make_ring(name: str, res: float) -> ItemCandidate:
    return ItemCandidate(
        item_id=f"id_{name}",
        name=name,
        base_type="Iron Ring",
        slot=SlotType.RING_1,
        slot_occupancy=SlotOccupancy.SINGLE_SLOT,
        slot_conflict_topology=SlotConflictTopology(
            occupied_slots=[SlotType.RING_1],
            conflicting_slots=[SlotType.RING_1],
        ),
        modifiers=[
            NormalizedModifier(
                modifier_type=NormalizedModifierType.LIGHTNING_RESISTANCE,
                scope=ModifierScope.GLOBAL_CHARACTER_STAT,
                value=res,
                raw_text=f"+{int(res)}% to Lightning Resistance",
            )
        ],
    )


def test_promote_candidate_increments_revision_and_reconciles_baseline():
    loadout = EquippedLoadout.create_draft(character_id="char_1")
    old_ring = make_ring("Old Ring", 40.0)
    loadout.set_slot(SlotType.RING_1, old_ring)
    loadout.finalize(loadout_id="loadout_1")
    assert loadout.revision == 1

    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="char_1",
        anchored_loadout_revision=1,
        lightning_res=75,
        lightning_raw=115,
        max_lightning_res=75,
    )

    new_ring = make_ring("New Ring", 10.0)
    updated_loadout, updated_baseline = promote_candidate_to_loadout(
        loadout=loadout,
        candidate=new_ring,
        slot=SlotType.RING_1,
        baseline=baseline,
    )

    assert updated_loadout.revision == 2
    assert updated_loadout.get_slot(SlotType.RING_1).item.name == "New Ring"
    assert updated_baseline is not None
    assert updated_baseline.anchored_loadout_revision == 2
    assert updated_baseline.raw_lightning_res.value == 85
    assert updated_baseline.effective_lightning_res.value == 75
