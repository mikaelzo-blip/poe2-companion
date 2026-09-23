"""Comprehensive unit tests for baseline/loadout revision lifecycles and initial setup."""

import json
from pathlib import Path
import pytest
from companion.state.provenance import VerificationState
from companion.equipment.baseline import (
    BaselineSource,
    CharacterFact,
    CharacterStatBaseline,
)
from companion.equipment.contribution import (
    ItemContribution,
    build_item_contribution,
)
from companion.equipment.baseline_gate import check_baseline_consistency
from companion.equipment.loadout import (
    EquippedLoadout,
    EquippedSlotEntry,
)
from companion.equipment.loadout_promotion import promote_candidate_to_loadout
from companion.equipment.reconciler import reconcile_baseline_after_swap
from companion.equipment.schema import (
    ItemCandidate,
    ModifierScope,
    NormalizedModifier,
    NormalizedModifierType,
    SlotConflictTopology,
    SlotOccupancy,
    SlotType,
)


def make_test_item(name: str, slot: SlotType, fire_res: float = 0.0, armour: int = 0) -> ItemCandidate:
    mods = []
    if fire_res > 0:
        mods.append(
            NormalizedModifier(
                modifier_type=NormalizedModifierType.FIRE_RESISTANCE,
                scope=ModifierScope.GLOBAL_CHARACTER_STAT,
                value=fire_res,
                raw_text=f"+{int(fire_res)}% to Fire Resistance",
            )
        )
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
        local_armour=armour,
        modifiers=mods,
    )


def test_initial_capture_multiple_items_does_not_simulate_swaps_or_increment_revision():
    loadout = EquippedLoadout.create_draft(character_id="char_1")
    initial_rev = loadout.revision

    helm = make_test_item("Iron Helm", SlotType.HELMET)
    body = make_test_item("Plate Vest", SlotType.BODY_ARMOUR)
    boots = make_test_item("Greaves", SlotType.BOOTS)

    loadout.set_slot(SlotType.HELMET, helm)
    loadout.set_slot(SlotType.BODY_ARMOUR, body)
    loadout.set_slot(SlotType.BOOTS, boots)

    # Revisions never increment during draft capture
    assert loadout.revision == initial_rev
    assert loadout.is_finalized is False


def test_finalized_loadout_starts_stable_revision_1():
    loadout = EquippedLoadout.create_draft(character_id="char_1")
    boots = make_test_item("Greaves", SlotType.BOOTS)
    loadout.set_slot(SlotType.BOOTS, boots)

    loadout.finalize(loadout_id="loadout_1")
    assert loadout.is_finalized is True
    assert loadout.revision == 1


def test_baseline_anchors_to_finalized_revision():
    loadout = EquippedLoadout.create_draft(character_id="char_1")
    loadout.finalize(loadout_id="loadout_1")

    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_1",
        character_id="char_1",
        anchored_loadout_revision=loadout.revision,
        life=1500,
    )
    assert baseline.anchored_loadout_revision == 1
    gate_res = check_baseline_consistency(baseline, loadout.revision)
    assert gate_res.is_consistent is True


def test_partial_loadout_retains_unknown_slots():
    loadout = EquippedLoadout.create_draft(character_id="char_1")
    boots = make_test_item("Greaves", SlotType.BOOTS)
    loadout.set_slot(SlotType.BOOTS, boots)
    loadout.finalize()

    assert SlotType.BOOTS in loadout.known_slots
    assert SlotType.HELMET in loadout.unknown_slots
    assert SlotType.BODY_ARMOUR in loadout.unknown_slots


def test_promote_candidate_increments_revision():
    loadout = EquippedLoadout.create_draft(character_id="char_1")
    old_ring = make_test_item("Old Ring", SlotType.RING_1, fire_res=20)
    loadout.set_slot(SlotType.RING_1, old_ring)
    loadout.finalize()
    assert loadout.revision == 1

    new_ring = make_test_item("New Ring", SlotType.RING_1, fire_res=35)
    updated_loadout, _ = promote_candidate_to_loadout(loadout, new_ring, SlotType.RING_1)
    assert updated_loadout.revision == 2


def test_safe_raw_resistance_rebase_produces_derived_calculation():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="c1",
        anchored_loadout_revision=1,
        fire_res=75,
        fire_raw=115,
        max_fire_res=75,
    )
    old_ring = build_item_contribution(make_test_item("Old Ring", SlotType.RING_1, fire_res=30))
    new_ring = build_item_contribution(make_test_item("New Ring", SlotType.RING_1, fire_res=10))

    reconciled = reconcile_baseline_after_swap(
        baseline=baseline,
        displaced_contributions=[old_ring],
        candidate_contribution=new_ring,
        new_loadout_revision=2,
    )
    assert reconciled.raw_fire_res.value == 95  # 115 - 30 + 10 = 95
    assert reconciled.effective_fire_res.value == 75  # min(95, 75)
    assert reconciled.effective_fire_res.source == BaselineSource.DERIVED_CALCULATION


def test_unsafe_armour_projection_marks_total_armour_stale():
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="c1",
        anchored_loadout_revision=1,
        armour=4200,
    )
    old_body = build_item_contribution(make_test_item("Old Body", SlotType.BODY_ARMOUR, armour=850))
    new_body = build_item_contribution(make_test_item("New Body", SlotType.BODY_ARMOUR, armour=1050))

    reconciled = reconcile_baseline_after_swap(
        baseline=baseline,
        displaced_contributions=[old_body],
        candidate_contribution=new_body,
        new_loadout_revision=2,
    )
    assert reconciled.armour.verification == VerificationState.STALE


def test_fresh_manual_baseline_reanchors_to_current_revision():
    loadout = EquippedLoadout.create_draft(character_id="char_1")
    loadout.finalize()
    loadout.revision = 4  # advanced to revision 4

    fresh_baseline = CharacterStatBaseline.create_partial(
        baseline_id="b_fresh",
        character_id="char_1",
        anchored_loadout_revision=loadout.revision,
        source=BaselineSource.MANUAL_USER_INPUT,
        verification=VerificationState.VERIFIED,
        life=1600,
    )
    assert fresh_baseline.anchored_loadout_revision == 4
    gate = check_baseline_consistency(fresh_baseline, loadout.revision)
    assert gate.is_consistent is True


def test_recommendation_alone_does_not_change_loadout_revision():
    loadout = EquippedLoadout.create_draft(character_id="char_1")
    loadout.finalize()
    assert loadout.revision == 1

    # Simulate inspection read-only
    cand = make_test_item("Cand Boots", SlotType.BOOTS, fire_res=20)
    contrib = build_item_contribution(cand)
    assert contrib.life_delta == 0.0

    # Stored loadout unchanged
    assert loadout.revision == 1


def test_persistence_reloads_revision_relationship(tmp_path: Path):
    loadout = EquippedLoadout.create_draft(character_id="char_1")
    loadout.finalize(loadout_id="loadout_persisted")
    loadout.revision = 3

    loadout_file = tmp_path / "loadout.json"
    loadout_file.write_text(loadout.model_dump_json(), encoding="utf-8")

    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_persisted",
        character_id="char_1",
        anchored_loadout_revision=3,
        life=1800,
    )
    baseline_file = tmp_path / "baseline.json"
    baseline_file.write_text(baseline.model_dump_json(), encoding="utf-8")

    # Reload
    reloaded_loadout = EquippedLoadout.model_validate_json(loadout_file.read_text(encoding="utf-8"))
    reloaded_baseline = CharacterStatBaseline.model_validate_json(baseline_file.read_text(encoding="utf-8"))

    assert reloaded_loadout.revision == 3
    assert reloaded_baseline.anchored_loadout_revision == 3
    gate = check_baseline_consistency(reloaded_baseline, reloaded_loadout.revision)
    assert gate.is_consistent is True
