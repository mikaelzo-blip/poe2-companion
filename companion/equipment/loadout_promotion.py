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
from companion.equipment.loadout import EquippedLoadout
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

    - Increments loadout.revision: N -> N+1
    - Displaces existing item in slot and any conflicting slots
    - Reconciles baseline if provided
    """
    wset = weapon_set or candidate.weapon_set

    # Find displaced entries
    displaced_contributions: list[ItemContribution] = []

    # Current item in the target slot
    current_entry = loadout.get_slot(slot, weapon_set=wset)
    if current_entry and current_entry.item:
        displaced_contributions.append(build_item_contribution(current_entry.item, target_weapon_set=wset))

    # If candidate is two-handed, also displace conflicting off-hand in that same weapon set
    if candidate.slot_occupancy == SlotOccupancy.TWO_HAND and wset in (WeaponSetContext.WEAPON_SET_1, WeaponSetContext.WEAPON_SET_2):
        for conflict_slot in candidate.slot_conflict_topology.conflicting_slots:
            if conflict_slot != slot:
                conflict_entry = loadout.get_slot(conflict_slot, weapon_set=wset)
                if conflict_entry and conflict_entry.item:
                    displaced_contributions.append(build_item_contribution(conflict_entry.item, target_weapon_set=wset))
                    loadout.clear_slot(conflict_slot, weapon_set=wset)

    # Increment revision
    loadout.revision += 1

    # Place candidate into slot
    loadout.set_slot(
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
        )

    return loadout, reconciled_baseline
