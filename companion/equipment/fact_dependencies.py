"""Centralized decision-relevant fact dependencies for equipment recommendations."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict

from companion.equipment.contribution import build_item_contribution
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.schema import (
    ItemCandidate,
    ModifierScope,
    NormalizedModifierType,
    SlotType,
    WeaponSetContext,
)
from companion.equipment.occupancy_contribution import compute_weapon_occupancy_contribution


class RecommendationFactDependencies(BaseModel):
    """Decision-relevant character stat fact dependencies for a recommendation."""

    model_config = ConfigDict(frozen=True)

    needs_armour: bool = False
    needs_evasion: bool = False
    needs_energy_shield: bool = False
    needs_movement_speed: bool = False
    needs_strength: bool = False
    needs_dexterity: bool = False
    needs_intelligence: bool = False
    needs_life: bool = False
    needs_fire_res: bool = False
    needs_cold_res: bool = False
    needs_lightning_res: bool = False
    needs_chaos_res: bool = False

    @property
    def any_defense_needed(self) -> bool:
        return self.needs_armour or self.needs_evasion or self.needs_energy_shield

    @property
    def any_attribute_needed(self) -> bool:
        return self.needs_strength or self.needs_dexterity or self.needs_intelligence

    @property
    def any_resistance_needed(self) -> bool:
        return (
            self.needs_fire_res
            or self.needs_cold_res
            or self.needs_lightning_res
            or self.needs_chaos_res
        )


def _has_armour_mods_or_mechanics(item: ItemCandidate) -> bool:
    for m in item.modifiers:
        if m.modifier_type in (
            NormalizedModifierType.LOCAL_ARMOUR,
            NormalizedModifierType.LOCAL_ARMOUR_AND_EVASION,
        ):
            return True
        raw = m.raw_text.lower()
        if "armour" in raw or "armor" in raw:
            return True
        if m.scope == ModifierScope.BUILD_MECHANIC and m.mechanic_id and (
            "armour" in m.mechanic_id.lower() or "armor" in m.mechanic_id.lower()
        ):
            return True
    return False


def _has_evasion_mods_or_mechanics(item: ItemCandidate) -> bool:
    for m in item.modifiers:
        if m.modifier_type in (
            NormalizedModifierType.LOCAL_EVASION,
            NormalizedModifierType.LOCAL_ARMOUR_AND_EVASION,
        ):
            return True
        raw = m.raw_text.lower()
        if "evasion" in raw:
            return True
        if m.scope == ModifierScope.BUILD_MECHANIC and m.mechanic_id and (
            "evasion" in m.mechanic_id.lower()
        ):
            return True
    return False


def _has_es_mods_or_mechanics(item: ItemCandidate) -> bool:
    for m in item.modifiers:
        if m.modifier_type == NormalizedModifierType.LOCAL_ENERGY_SHIELD:
            return True
        raw = m.raw_text.lower()
        if "energy shield" in raw:
            return True
        if m.scope == ModifierScope.BUILD_MECHANIC and m.mechanic_id:
            mech = m.mechanic_id.lower()
            if "energy_shield" in mech or mech in ("ci", "chaos_inoculation", "eldritch_battery"):
                return True
    return False


def determine_recommendation_fact_dependencies(
    candidate: ItemCandidate,
    loadout: EquippedLoadout | None = None,
    slot: SlotType | None = None,
    weapon_set: WeaponSetContext | None = None,
    cascade_result: Any | None = None,
    projection: Any | None = None,
    evaluates_deficits: bool = False,
) -> RecommendationFactDependencies:
    """Determine which character baseline facts are required to safely evaluate candidate.

    Derivations:
    - needs_armour: cand.local_armour != disp_armour or candidate has armour mods/mechanics.
    - needs_evasion: cand.local_evasion != disp_evasion or candidate has evasion mods/mechanics.
    - needs_energy_shield: cand.local_energy_shield != disp_es or candidate has ES mods.
    - needs_movement_speed: cand_ms != disp_ms.
    - needs_strength: cand_str != disp_str or candidate/cascade requires Strength.
    - needs_dexterity: cand_dex != disp_dex or candidate/cascade requires Dexterity.
    - needs_intelligence: cand_int != disp_int or candidate/cascade requires Intelligence.
    - needs_life: cand_life != disp_life.
    - needs_fire_res, needs_cold_res, needs_lightning_res, needs_chaos_res:
      candidate changes res or resistance evaluation evaluates deficits.
    """
    displaced_items: list[ItemCandidate] = []
    if projection is not None and hasattr(projection, "displaced_items"):
        displaced_items = list(projection.displaced_items)
    elif loadout is not None and slot is not None:
        is_weapon_slot = slot in (SlotType.MAIN_HAND, SlotType.OFF_HAND)
        if is_weapon_slot:
            wset = weapon_set or candidate.weapon_set or WeaponSetContext.WEAPON_SET_1
            occ = compute_weapon_occupancy_contribution(loadout, candidate, target_set=wset)
            displaced_items = [e.item for e in occ.displaced_entries if e.item is not None]
        else:
            entry = loadout.get_slot(slot, weapon_set or candidate.weapon_set)
            if entry and entry.item:
                displaced_items = [entry.item]

    cand_armour = candidate.local_armour
    disp_armour = sum(i.local_armour for i in displaced_items)
    cand_evasion = candidate.local_evasion
    disp_evasion = sum(i.local_evasion for i in displaced_items)
    cand_es = candidate.local_energy_shield
    disp_es = sum(i.local_energy_shield for i in displaced_items)

    if projection is not None and hasattr(projection, "movement_speed"):
        armour_delta = getattr(projection, "armour", None)
        armour_delta_val = armour_delta.delta if armour_delta is not None else 0.0
        local_armour_delta_val = getattr(projection, "local_armour_delta", 0)

        evasion_delta = getattr(projection, "evasion", None)
        evasion_delta_val = evasion_delta.delta if evasion_delta is not None else 0.0
        local_evasion_delta_val = getattr(projection, "local_evasion_delta", 0)

        es_delta = getattr(projection, "energy_shield", None)
        es_delta_val = es_delta.delta if es_delta is not None else 0.0
        local_es_delta_val = getattr(projection, "local_energy_shield_delta", 0)

        ms_delta = projection.movement_speed.delta
        life_delta = projection.life.delta
        fire_delta = projection.fire_res.delta
        cold_delta = projection.cold_res.delta
        light_delta = projection.lightning_res.delta
        chaos_delta = projection.chaos_res.delta
        str_delta = projection.strength.delta
        dex_delta = projection.dexterity.delta
        int_delta = projection.intelligence.delta
    else:
        cand_contrib = build_item_contribution(candidate, target_weapon_set=weapon_set)
        disp_contribs = [build_item_contribution(i) for i in displaced_items]

        local_armour_delta_val = cand_armour - disp_armour
        armour_delta_val = float(local_armour_delta_val)

        local_evasion_delta_val = cand_evasion - disp_evasion
        evasion_delta_val = float(local_evasion_delta_val)

        local_es_delta_val = cand_es - disp_es
        es_delta_val = float(local_es_delta_val)

        disp_ms = sum(c.movement_speed_delta for c in disp_contribs)
        ms_delta = cand_contrib.movement_speed_delta - disp_ms

        disp_life = sum(c.life_delta for c in disp_contribs)
        life_delta = cand_contrib.life_delta - disp_life

        disp_fire = sum(c.fire_res_delta for c in disp_contribs)
        fire_delta = cand_contrib.fire_res_delta - disp_fire

        disp_cold = sum(c.cold_res_delta for c in disp_contribs)
        cold_delta = cand_contrib.cold_res_delta - disp_cold

        disp_light = sum(c.lightning_res_delta for c in disp_contribs)
        light_delta = cand_contrib.lightning_res_delta - disp_light

        disp_chaos = sum(c.chaos_res_delta for c in disp_contribs)
        chaos_delta = cand_contrib.chaos_res_delta - disp_chaos

        disp_str = sum(c.str_delta for c in disp_contribs)
        str_delta = float(cand_contrib.str_delta - disp_str)

        disp_dex = sum(c.dex_delta for c in disp_contribs)
        dex_delta = float(cand_contrib.dex_delta - disp_dex)

        disp_int = sum(c.int_delta for c in disp_contribs)
        int_delta = float(cand_contrib.int_delta - disp_int)

    cand_has_armour = _has_armour_mods_or_mechanics(candidate)
    disp_has_armour = any(_has_armour_mods_or_mechanics(i) for i in displaced_items)
    needs_armour = bool(
        cand_armour != disp_armour
        or cand_has_armour
        or disp_has_armour
        or armour_delta_val != 0
        or local_armour_delta_val != 0
    )

    cand_has_evasion = _has_evasion_mods_or_mechanics(candidate)
    disp_has_evasion = any(_has_evasion_mods_or_mechanics(i) for i in displaced_items)
    needs_evasion = bool(
        cand_evasion != disp_evasion
        or cand_has_evasion
        or disp_has_evasion
        or evasion_delta_val != 0
        or local_evasion_delta_val != 0
    )

    cand_has_es = _has_es_mods_or_mechanics(candidate)
    disp_has_es = any(_has_es_mods_or_mechanics(i) for i in displaced_items)
    needs_energy_shield = bool(
        cand_es != disp_es
        or cand_has_es
        or disp_has_es
        or es_delta_val != 0
        or local_es_delta_val != 0
    )

    needs_movement_speed = bool(ms_delta != 0)

    cascade_requires_str = False
    cascade_requires_dex = False
    cascade_requires_int = False
    if cascade_result is not None:
        all_defs = (
            getattr(cascade_result, "candidate_deficiencies", [])
            + getattr(cascade_result, "loadout_cascading_deficiencies", [])
            + getattr(cascade_result, "gem_cascading_deficiencies", [])
        )
        cascade_requires_str = any(getattr(d, "attribute", "") == "str" for d in all_defs)
        cascade_requires_dex = any(getattr(d, "attribute", "") == "dex" for d in all_defs)
        cascade_requires_int = any(getattr(d, "attribute", "") == "int" for d in all_defs)

    needs_strength = bool(str_delta != 0 or candidate.required_str > 0 or cascade_requires_str)
    needs_dexterity = bool(dex_delta != 0 or candidate.required_dex > 0 or cascade_requires_dex)
    needs_intelligence = bool(int_delta != 0 or candidate.required_int > 0 or cascade_requires_int)

    needs_life = bool(life_delta != 0)
    needs_fire_res = bool(fire_delta != 0 or evaluates_deficits)
    needs_cold_res = bool(cold_delta != 0 or evaluates_deficits)
    needs_lightning_res = bool(light_delta != 0 or evaluates_deficits)
    needs_chaos_res = bool(chaos_delta != 0 or evaluates_deficits)

    return RecommendationFactDependencies(
        needs_armour=needs_armour,
        needs_evasion=needs_evasion,
        needs_energy_shield=needs_energy_shield,
        needs_movement_speed=needs_movement_speed,
        needs_strength=needs_strength,
        needs_dexterity=needs_dexterity,
        needs_intelligence=needs_intelligence,
        needs_life=needs_life,
        needs_fire_res=needs_fire_res,
        needs_cold_res=needs_cold_res,
        needs_lightning_res=needs_lightning_res,
        needs_chaos_res=needs_chaos_res,
    )
