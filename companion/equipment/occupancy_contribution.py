"""OccupancyContribution tracking displaced weapon set slots and stat subtractions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from companion.equipment.contribution import ItemContribution, build_item_contribution
from companion.equipment.loadout import EquippedLoadout, EquippedSlotEntry
from companion.equipment.schema import ItemCandidate, SlotOccupancy, SlotType, WeaponSetContext


class OccupancyContribution(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    target_weapon_set: WeaponSetContext
    candidate: ItemCandidate
    displaced_entries: list[EquippedSlotEntry] = Field(default_factory=list)
    displaced_contributions: list[ItemContribution] = Field(default_factory=list)
    candidate_contribution: ItemContribution

    @property
    def displaced_fire_res(self) -> float:
        return sum(c.fire_res_delta for c in self.displaced_contributions)

    @property
    def displaced_cold_res(self) -> float:
        return sum(c.cold_res_delta for c in self.displaced_contributions)

    @property
    def displaced_lightning_res(self) -> float:
        return sum(c.lightning_res_delta for c in self.displaced_contributions)

    @property
    def displaced_chaos_res(self) -> float:
        return sum(c.chaos_res_delta for c in self.displaced_contributions)

    @property
    def displaced_life(self) -> float:
        return sum(c.life_delta for c in self.displaced_contributions)

    @property
    def displaced_str(self) -> int:
        return sum(c.str_delta for c in self.displaced_contributions)

    @property
    def displaced_dex(self) -> int:
        return sum(c.dex_delta for c in self.displaced_contributions)

    @property
    def displaced_int(self) -> int:
        return sum(c.int_delta for c in self.displaced_contributions)

    @property
    def candidate_fire_res(self) -> float:
        return self.candidate_contribution.fire_res_delta

    @property
    def candidate_cold_res(self) -> float:
        return self.candidate_contribution.cold_res_delta

    @property
    def candidate_lightning_res(self) -> float:
        return self.candidate_contribution.lightning_res_delta

    @property
    def candidate_chaos_res(self) -> float:
        return self.candidate_contribution.chaos_res_delta

    @property
    def candidate_life(self) -> float:
        return self.candidate_contribution.life_delta

    @property
    def candidate_str(self) -> int:
        return self.candidate_contribution.str_delta

    @property
    def candidate_dex(self) -> int:
        return self.candidate_contribution.dex_delta

    @property
    def candidate_int(self) -> int:
        return self.candidate_contribution.int_delta

    @property
    def net_fire_res_delta(self) -> float:
        return self.candidate_fire_res - self.displaced_fire_res

    @property
    def net_cold_res_delta(self) -> float:
        return self.candidate_cold_res - self.displaced_cold_res

    @property
    def net_lightning_res_delta(self) -> float:
        return self.candidate_lightning_res - self.displaced_lightning_res

    @property
    def net_chaos_res_delta(self) -> float:
        return self.candidate_chaos_res - self.displaced_chaos_res

    @property
    def net_life_delta(self) -> float:
        return self.candidate_life - self.displaced_life

    @property
    def net_str_delta(self) -> int:
        return self.candidate_str - self.displaced_str

    @property
    def net_dex_delta(self) -> int:
        return self.candidate_dex - self.displaced_dex

    @property
    def net_int_delta(self) -> int:
        return self.candidate_int - self.displaced_int


def compute_weapon_occupancy_contribution(
    loadout: EquippedLoadout,
    candidate: ItemCandidate,
    target_set: WeaponSetContext,
) -> OccupancyContribution:
    weapon_dict = (
        loadout.weapon_set_1
        if target_set == WeaponSetContext.WEAPON_SET_1
        else loadout.weapon_set_2
    )

    displaced_entries: list[EquippedSlotEntry] = []
    mh_entry = weapon_dict.get(SlotType.MAIN_HAND.value)
    oh_entry = weapon_dict.get(SlotType.OFF_HAND.value)

    if candidate.slot_occupancy == SlotOccupancy.TWO_HAND:
        if mh_entry:
            displaced_entries.append(mh_entry)
        if oh_entry:
            displaced_entries.append(oh_entry)
    elif candidate.slot == SlotType.MAIN_HAND:
        if mh_entry:
            displaced_entries.append(mh_entry)
        # If existing main hand was two-handed, off hand is also displaced
        if mh_entry and mh_entry.item.slot_occupancy == SlotOccupancy.TWO_HAND:
            if oh_entry and oh_entry not in displaced_entries:
                displaced_entries.append(oh_entry)
    elif candidate.slot == SlotType.OFF_HAND:
        if oh_entry:
            displaced_entries.append(oh_entry)
        # If existing main hand is two-handed, cannot keep it with an off hand
        if mh_entry and mh_entry.item.slot_occupancy == SlotOccupancy.TWO_HAND:
            if mh_entry not in displaced_entries:
                displaced_entries.append(mh_entry)

    displaced_contribs = [
        build_item_contribution(entry.item, target_weapon_set=target_set)
        for entry in displaced_entries
    ]
    cand_contrib = build_item_contribution(candidate, target_weapon_set=target_set)

    return OccupancyContribution(
        target_weapon_set=target_set,
        candidate=candidate,
        displaced_entries=displaced_entries,
        displaced_contributions=displaced_contribs,
        candidate_contribution=cand_contrib,
    )
