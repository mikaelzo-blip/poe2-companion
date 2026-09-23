"""Partial projection engine isolating verified item deltas from unverified absolute stats."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from companion.state.provenance import VerificationState
from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.contribution import ItemContribution, build_item_contribution
from companion.equipment.loadout import EquippedLoadout, EquippedSlotEntry
from companion.equipment.occupancy_contribution import compute_weapon_occupancy_contribution
from companion.equipment.resistance import (
    ResistanceProjection,
    ResistanceType,
    evaluate_resistance_delta,
)
from companion.equipment.schema import ItemCandidate, SlotOccupancy, SlotType, WeaponSetContext


class StatProjection(BaseModel):
    model_config = ConfigDict(frozen=True)

    delta: float = 0.0
    is_delta_known: bool = True
    projected_absolute: int | float | None = None
    projected_raw: int | None = None
    projected_overcap: int | None = None
    is_absolute_known: bool = False
    verification: VerificationState = VerificationState.VERIFIED


class PartialLoadoutProjection(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    slot: SlotType
    target_weapon_set: WeaponSetContext | None = None
    candidate: ItemCandidate
    displaced_items: list[ItemCandidate] = Field(default_factory=list)
    life: StatProjection
    armour: StatProjection
    evasion: StatProjection
    energy_shield: StatProjection
    fire_res: StatProjection
    cold_res: StatProjection
    lightning_res: StatProjection
    chaos_res: StatProjection
    strength: StatProjection
    dexterity: StatProjection
    intelligence: StatProjection
    movement_speed: StatProjection
    local_armour_delta: int = 0
    local_evasion_delta: int = 0
    local_energy_shield_delta: int = 0
    is_baseline_stale: bool = False
    baseline_anchored_revision: int | None = None


def project_candidate_on_loadout(
    loadout: EquippedLoadout,
    candidate: ItemCandidate,
    slot: SlotType,
    baseline: CharacterStatBaseline | None = None,
    weapon_set: WeaponSetContext | None = None,
) -> PartialLoadoutProjection:
    displaced_items: list[ItemCandidate] = []
    displaced_contribs: list[ItemContribution] = []
    cand_contrib = build_item_contribution(candidate, target_weapon_set=weapon_set)

    is_weapon_slot = slot in (SlotType.MAIN_HAND, SlotType.OFF_HAND)
    if is_weapon_slot:
        wset = weapon_set or WeaponSetContext.WEAPON_SET_1
        occ = compute_weapon_occupancy_contribution(loadout, candidate, target_set=wset)
        displaced_items = [e.item for e in occ.displaced_entries]
        displaced_contribs = occ.displaced_contributions
    else:
        entry = loadout.get_slot(slot)
        if entry and entry.item:
            displaced_items = [entry.item]
            displaced_contribs = [build_item_contribution(entry.item)]

    # Aggregate displaced totals
    disp_life = sum(c.life_delta for c in displaced_contribs)
    disp_fire = sum(c.fire_res_delta for c in displaced_contribs)
    disp_cold = sum(c.cold_res_delta for c in displaced_contribs)
    disp_light = sum(c.lightning_res_delta for c in displaced_contribs)
    disp_chaos = sum(c.chaos_res_delta for c in displaced_contribs)
    disp_str = sum(c.str_delta for c in displaced_contribs)
    disp_dex = sum(c.dex_delta for c in displaced_contribs)
    disp_int = sum(c.int_delta for c in displaced_contribs)
    disp_ms = sum(c.movement_speed_delta for c in displaced_contribs)
    disp_armour = sum(c.local_armour for c in displaced_contribs)
    disp_evasion = sum(c.local_evasion for c in displaced_contribs)
    disp_es = sum(c.local_energy_shield for c in displaced_contribs)

    net_life = cand_contrib.life_delta - disp_life
    net_fire = cand_contrib.fire_res_delta - disp_fire
    net_cold = cand_contrib.cold_res_delta - disp_cold
    net_light = cand_contrib.lightning_res_delta - disp_light
    net_chaos = cand_contrib.chaos_res_delta - disp_chaos
    net_str = cand_contrib.str_delta - disp_str
    net_dex = cand_contrib.dex_delta - disp_dex
    net_int = cand_contrib.int_delta - disp_int
    net_ms = cand_contrib.movement_speed_delta - disp_ms
    local_armour_delta = cand_contrib.local_armour - disp_armour
    local_evasion_delta = cand_contrib.local_evasion - disp_evasion
    local_es_delta = cand_contrib.local_energy_shield - disp_es

    is_stale = False
    if baseline:
        is_stale = baseline.anchored_loadout_revision != loadout.revision

    # Resistances via dynamic resistance engine
    def make_res_proj(res_type: ResistanceType, delta: float) -> StatProjection:
        eval_proj = evaluate_resistance_delta(baseline, res_type, delta)
        is_known = eval_proj.projected_effective is not None and not is_stale
        return StatProjection(
            delta=delta,
            is_delta_known=True,
            projected_absolute=eval_proj.projected_effective if not is_stale else None,
            projected_raw=eval_proj.projected_raw if not is_stale else None,
            projected_overcap=eval_proj.projected_overcap_buffer if not is_stale else None,
            is_absolute_known=is_known,
            verification=VerificationState.VERIFIED if is_known else VerificationState.UNKNOWN,
        )

    # Linear stats
    def make_linear_proj(delta: float, fact_val: int | None, is_known_fact: bool) -> StatProjection:
        if baseline and is_known_fact and fact_val is not None and not is_stale:
            return StatProjection(
                delta=delta,
                is_delta_known=True,
                projected_absolute=fact_val + int(delta),
                is_absolute_known=True,
                verification=VerificationState.VERIFIED,
            )
        return StatProjection(
            delta=delta,
            is_delta_known=True,
            projected_absolute=None,
            is_absolute_known=False,
            verification=VerificationState.UNKNOWN,
        )

    # Complex non-linear defenses (never fabricate absolute)
    def make_defense_proj(local_delta: int, fact_val: int | None, is_known_fact: bool) -> StatProjection:
        return StatProjection(
            delta=float(local_delta),
            is_delta_known=True,
            projected_absolute=None,  # isolated non-linear defense
            is_absolute_known=False,
            verification=VerificationState.UNKNOWN,
        )

    life_val = baseline.life.value if baseline else None
    life_known = baseline.life.is_known if baseline else False

    str_val = baseline.strength.value if baseline else None
    str_known = baseline.strength.is_known if baseline else False

    dex_val = baseline.dexterity.value if baseline else None
    dex_known = baseline.dexterity.is_known if baseline else False

    int_val = baseline.intelligence.value if baseline else None
    int_known = baseline.intelligence.is_known if baseline else False

    ms_val = baseline.movement_speed.value if baseline else None
    ms_known = baseline.movement_speed.is_known if baseline else False

    armour_val = baseline.armour.value if baseline else None
    armour_known = baseline.armour.is_known if baseline else False

    eva_val = baseline.evasion.value if baseline else None
    eva_known = baseline.evasion.is_known if baseline else False

    es_val = baseline.energy_shield.value if baseline else None
    es_known = baseline.energy_shield.is_known if baseline else False

    return PartialLoadoutProjection(
        slot=slot,
        target_weapon_set=weapon_set,
        candidate=candidate,
        displaced_items=displaced_items,
        life=make_linear_proj(net_life, life_val, life_known),
        armour=make_defense_proj(local_armour_delta, armour_val, armour_known),
        evasion=make_defense_proj(local_evasion_delta, eva_val, eva_known),
        energy_shield=make_defense_proj(local_es_delta, es_val, es_known),
        fire_res=make_res_proj(ResistanceType.FIRE, net_fire),
        cold_res=make_res_proj(ResistanceType.COLD, net_cold),
        lightning_res=make_res_proj(ResistanceType.LIGHTNING, net_light),
        chaos_res=make_res_proj(ResistanceType.CHAOS, net_chaos),
        strength=make_linear_proj(net_str, str_val, str_known),
        dexterity=make_linear_proj(net_dex, dex_val, dex_known),
        intelligence=make_linear_proj(net_int, int_val, int_known),
        movement_speed=make_linear_proj(net_ms, ms_val, ms_known),
        local_armour_delta=local_armour_delta,
        local_evasion_delta=local_evasion_delta,
        local_energy_shield_delta=local_es_delta,
        is_baseline_stale=is_stale,
        baseline_anchored_revision=baseline.anchored_loadout_revision if baseline else None,
    )
