"""Candidate promotion service for updating loadout state and reconciling baseline."""

from __future__ import annotations

from companion.equipment.baseline import (
    BaselineSource,
    CharacterStatBaseline,
)
from companion.equipment.contribution import (
    ItemContribution,
    build_item_contribution,
)
from companion.equipment.loadout import EquippedLoadout, is_item_decision_equal
from companion.equipment.reconciler import reconcile_baseline_after_swap
from companion.equipment.schema import (
    ItemCandidate,
    SlotOccupancy,
    SlotType,
    WeaponSetContext,
)


def promote_candidate_to_loadout(
    loadout: EquippedLoadout,
    candidate: ItemCandidate,
    slot: SlotType,
    baseline: CharacterStatBaseline | None = None,
    weapon_set: WeaponSetContext | None = None,
) -> tuple[EquippedLoadout, CharacterStatBaseline | None]:
    """Promote an evaluated candidate item to equipped loadout status.

    - Increments loadout.revision: N -> N+1 exactly once if finalized and changed
    - No-op if candidate is identical to current slot and no conflicts displaced
    - Displaces existing item in slot and any conflicting slots
    - Reconciles baseline if provided, anchoring new revision and fingerprint
    """
    wset = weapon_set or candidate.weapon_set

    # Find displaced entries
    displaced_contributions: list[ItemContribution] = []

    # Current item in the target slot
    current_entry = loadout.get_slot(slot, weapon_set=wset)
    current_item = current_entry.item if current_entry else None

    # Check conflicts
    conflicting_entries: list[tuple[SlotType, ItemCandidate]] = []
    if candidate.slot_occupancy == SlotOccupancy.TWO_HAND and wset in (WeaponSetContext.WEAPON_SET_1, WeaponSetContext.WEAPON_SET_2):
        for conflict_slot in candidate.slot_conflict_topology.conflicting_slots:
            if conflict_slot != slot:
                conflict_entry = loadout.get_slot(conflict_slot, weapon_set=wset)
                if conflict_entry and conflict_entry.item:
                    conflicting_entries.append((conflict_slot, conflict_entry.item))

    # Determine whether content actually changes
    is_changed = True
    if is_item_decision_equal(current_item, candidate) and len(conflicting_entries) == 0:
        is_changed = False

    if is_changed:
        if current_item:
            displaced_contributions.append(build_item_contribution(current_item, target_weapon_set=wset))

        for conflict_slot, conf_item in conflicting_entries:
            displaced_contributions.append(build_item_contribution(conf_item, target_weapon_set=wset))
            loadout._raw_clear_slot(conflict_slot, weapon_set=wset)

        if loadout.is_finalized:
            loadout.revision += 1

        loadout._raw_set_slot(
            slot=slot,
            item=candidate,
            source=BaselineSource.CLIPBOARD_ITEM_TEXT,
            weapon_set=wset,
        )

    candidate_contrib = build_item_contribution(candidate, target_weapon_set=wset)

    # Reconcile baseline if provided
    reconciled_baseline: CharacterStatBaseline | None = None
    if baseline:
        reconciled_baseline = reconcile_baseline_after_swap(
            baseline=baseline,
            displaced_contributions=displaced_contributions,
            candidate_contribution=candidate_contrib,
            new_loadout_revision=loadout.revision,
            new_loadout_fingerprint=loadout.compute_fingerprint(),
        )

    return loadout, reconciled_baseline
