"""ItemContribution aggregation layer for character deltas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from companion.equipment.schema import (
    ItemCandidate,
    ModifierScope,
    NormalizedModifier,
    NormalizedModifierType,
    SlotConflictTopology,
    SlotOccupancy,
    SlotType,
    WeaponSetContext,
)


class ItemContribution(BaseModel):
    """Aggregated character-relevant contributions from an equipped or candidate item."""

    model_config = ConfigDict(frozen=True)

    item_id: str
    slot: SlotType
    slot_occupancy: SlotOccupancy = SlotOccupancy.SINGLE_SLOT
    slot_conflict_topology: SlotConflictTopology = Field(
        default_factory=lambda: SlotConflictTopology(occupied_slots=[])
    )
    target_weapon_set: WeaponSetContext | None = None
    life_delta: float = 0.0
    fire_res_delta: float = 0.0
    cold_res_delta: float = 0.0
    lightning_res_delta: float = 0.0
    chaos_res_delta: float = 0.0
    str_delta: int = 0
    dex_delta: int = 0
    int_delta: int = 0
    movement_speed_delta: float = 0.0
    local_armour: int = 0
    local_evasion: int = 0
    local_energy_shield: int = 0
    global_modifiers: list[NormalizedModifier] = Field(default_factory=list)
    weapon_set_modifiers: list[NormalizedModifier] = Field(default_factory=list)
    build_mechanic_modifiers: list[NormalizedModifier] = Field(default_factory=list)
    unknown_modifiers: list[NormalizedModifier] = Field(default_factory=list)


def build_item_contribution(
    item: ItemCandidate | None,
    target_weapon_set: WeaponSetContext | None = None,
) -> ItemContribution:
    """Aggregate character contributions from an ItemCandidate."""
    if item is None:
        return ItemContribution(
            item_id="empty",
            slot=SlotType.HELMET,
            slot_occupancy=SlotOccupancy.SINGLE_SLOT,
            slot_conflict_topology=SlotConflictTopology(occupied_slots=[]),
            target_weapon_set=target_weapon_set,
        )

    wset = target_weapon_set or item.weapon_set

    life = 0.0
    fire_res = 0.0
    cold_res = 0.0
    light_res = 0.0
    chaos_res = 0.0
    str_val = 0
    dex_val = 0
    int_val = 0
    ms_val = 0.0

    global_mods: list[NormalizedModifier] = []
    weapon_set_mods: list[NormalizedModifier] = []
    build_mechanic_mods: list[NormalizedModifier] = []
    unknown_mods: list[NormalizedModifier] = []

    for mod in item.modifiers:
        if mod.scope == ModifierScope.GLOBAL_CHARACTER_STAT:
            global_mods.append(mod)
            if mod.modifier_type == NormalizedModifierType.MAXIMUM_LIFE:
                life += mod.value
            elif mod.modifier_type == NormalizedModifierType.FIRE_RESISTANCE:
                fire_res += mod.value
            elif mod.modifier_type == NormalizedModifierType.COLD_RESISTANCE:
                cold_res += mod.value
            elif mod.modifier_type == NormalizedModifierType.LIGHTNING_RESISTANCE:
                light_res += mod.value
            elif mod.modifier_type == NormalizedModifierType.CHAOS_RESISTANCE:
                chaos_res += mod.value
            elif mod.modifier_type == NormalizedModifierType.STRENGTH:
                str_val += int(mod.value)
            elif mod.modifier_type == NormalizedModifierType.DEXTERITY:
                dex_val += int(mod.value)
            elif mod.modifier_type == NormalizedModifierType.INTELLIGENCE:
                int_val += int(mod.value)
            elif mod.modifier_type == NormalizedModifierType.MOVEMENT_SPEED:
                ms_val += mod.value
        elif mod.scope == ModifierScope.BUILD_MECHANIC:
            build_mechanic_mods.append(mod)
        elif mod.scope in (ModifierScope.UNKNOWN_SCOPE, ModifierScope.CONDITIONAL):
            unknown_mods.append(mod)

    return ItemContribution(
        item_id=item.item_id,
        slot=item.slot,
        slot_occupancy=item.slot_occupancy,
        slot_conflict_topology=item.slot_conflict_topology,
        target_weapon_set=wset,
        life_delta=life,
        fire_res_delta=fire_res,
        cold_res_delta=cold_res,
        lightning_res_delta=light_res,
        chaos_res_delta=chaos_res,
        str_delta=str_val,
        dex_delta=dex_val,
        int_delta=int_val,
        movement_speed_delta=ms_val,
        local_armour=item.local_armour,
        local_evasion=item.local_evasion,
        local_energy_shield=item.local_energy_shield,
        global_modifiers=global_mods,
        weapon_set_modifiers=weapon_set_mods,
        build_mechanic_modifiers=build_mechanic_mods,
        unknown_modifiers=unknown_mods,
    )
