"""Unit tests for post-setup baseline reconciler and Resistance Rebase Policy."""

import pytest
from companion.state.provenance import VerificationState
from companion.equipment.baseline import (
    BaselineSource,
    CharacterStatBaseline,
)
from companion.equipment.contribution import ItemContribution
from companion.equipment.schema import SlotConflictTopology, SlotOccupancy, SlotType
from companion.equipment.reconciler import reconcile_baseline_after_swap


def make_dummy_contrib(
    item_id: str,
    slot: SlotType,
    fire_res: float = 0.0,
    lightning_res: float = 0.0,
    str_delta: int = 0,
    local_armour: int = 0,
) -> ItemContribution:
    return ItemContribution(
        item_id=item_id,
        slot=slot,
        slot_occupancy=SlotOccupancy.SINGLE_SLOT,
        slot_conflict_topology=SlotConflictTopology(occupied_slots=[slot]),
        fire_res_delta=fire_res,
        lightning_res_delta=lightning_res,
        str_delta=str_delta,
        local_armour=local_armour,
    )


def test_reconcile_resistance_with_known_raw():
    # Raw 115, Cap 75, Effective 75. Old item +40, New item +10 -> net -30
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="c1",
        anchored_loadout_revision=1,
        lightning_res=75,
        lightning_raw=115,
        max_lightning_res=75,
    )
    old_item = make_dummy_contrib("old_ring", SlotType.RING_1, lightning_res=40.0)
    new_item = make_dummy_contrib("new_ring", SlotType.RING_1, lightning_res=10.0)

    reconciled = reconcile_baseline_after_swap(
        baseline=baseline,
        displaced_contributions=[old_item],
        candidate_contribution=new_item,
        new_loadout_revision=2,
    )
    assert reconciled.anchored_loadout_revision == 2
    assert reconciled.raw_lightning_res.value == 85  # 115 - 40 + 10 = 85
    assert reconciled.effective_lightning_res.value == 75  # min(85, 75) = 75
    assert reconciled.lightning_overcap_buffer.value == 10
    assert reconciled.effective_lightning_res.source == BaselineSource.DERIVED_CALCULATION


def test_reconcile_resistance_loss_exceeding_overcap():
    # Raw 80, Cap 75, Effective 75. Loss 10 -> new raw 70, effective 70
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="c1",
        anchored_loadout_revision=1,
        lightning_res=75,
        lightning_raw=80,
        max_lightning_res=75,
    )
    old_item = make_dummy_contrib("old_ring", SlotType.RING_1, lightning_res=20.0)
    new_item = make_dummy_contrib("new_ring", SlotType.RING_1, lightning_res=10.0)

    reconciled = reconcile_baseline_after_swap(
        baseline=baseline,
        displaced_contributions=[old_item],
        candidate_contribution=new_item,
        new_loadout_revision=2,
    )
    assert reconciled.raw_lightning_res.value == 70
    assert reconciled.effective_lightning_res.value == 70
    assert reconciled.lightning_overcap_buffer.value == 0


def test_reconcile_resistance_unknown_raw_marks_stale():
    # Effective 75, but raw is UNKNOWN. Swap loses 30% resistance.
    # Reconciler must NOT compute 75 - 30 = 45. It must mark effective resistance STALE!
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="c1",
        anchored_loadout_revision=1,
        lightning_res=75,
        lightning_raw=None,  # Unknown raw!
    )
    old_item = make_dummy_contrib("old_ring", SlotType.RING_1, lightning_res=40.0)
    new_item = make_dummy_contrib("new_ring", SlotType.RING_1, lightning_res=10.0)

    reconciled = reconcile_baseline_after_swap(
        baseline=baseline,
        displaced_contributions=[old_item],
        candidate_contribution=new_item,
        new_loadout_revision=2,
    )
    assert reconciled.raw_lightning_res.value is None
    assert reconciled.effective_lightning_res.verification in (
        VerificationState.STALE,
        VerificationState.UNKNOWN,
    )


def test_reconcile_linear_attributes_safely_rebases():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="c1",
        anchored_loadout_revision=1,
        strength=100,
    )
    old_item = make_dummy_contrib("old_amulet", SlotType.AMULET, str_delta=15)
    new_item = make_dummy_contrib("new_amulet", SlotType.AMULET, str_delta=25)

    reconciled = reconcile_baseline_after_swap(
        baseline=baseline,
        displaced_contributions=[old_item],
        candidate_contribution=new_item,
        new_loadout_revision=2,
    )
    assert reconciled.strength.value == 110  # 100 - 15 + 25
    assert reconciled.strength.source == BaselineSource.DERIVED_CALCULATION


def test_reconcile_complex_armour_marked_stale():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="c1",
        anchored_loadout_revision=1,
        armour=4200,
    )
    old_item = make_dummy_contrib("old_chest", SlotType.BODY_ARMOUR, local_armour=850)
    new_item = make_dummy_contrib("new_chest", SlotType.BODY_ARMOUR, local_armour=1050)

    reconciled = reconcile_baseline_after_swap(
        baseline=baseline,
        displaced_contributions=[old_item],
        candidate_contribution=new_item,
        new_loadout_revision=2,
    )
    # Armour is marked STALE rather than fabricating 4400
    assert reconciled.armour.verification == VerificationState.STALE
