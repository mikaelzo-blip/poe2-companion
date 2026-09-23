"""Slot-specific evaluation weights and priorities."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from companion.equipment.contribution import build_item_contribution
from companion.equipment.schema import ItemCandidate, SlotType


class SlotEvaluationWeights(BaseModel):
    model_config = ConfigDict(frozen=True)

    life_weight: float = 1.0
    res_weight: float = 1.5
    movement_speed_weight: float = 1.0
    defense_weight: float = 0.05
    attribute_weight: float = 0.5


def get_slot_weights(slot: SlotType) -> SlotEvaluationWeights:
    if slot == SlotType.BOOTS:
        return SlotEvaluationWeights(
            life_weight=1.0,
            res_weight=1.2,
            movement_speed_weight=3.5,
            defense_weight=0.05,
            attribute_weight=0.5,
        )
    if slot == SlotType.BODY_ARMOUR:
        return SlotEvaluationWeights(
            life_weight=1.5,
            res_weight=1.2,
            movement_speed_weight=0.0,
            defense_weight=1.5,
            attribute_weight=0.5,
        )
    if slot in (SlotType.RING_1, SlotType.RING_2, SlotType.AMULET, SlotType.BELT):
        return SlotEvaluationWeights(
            life_weight=1.2,
            res_weight=1.5,
            movement_speed_weight=0.0,
            defense_weight=0.0,
            attribute_weight=0.8,
        )
    if slot in (SlotType.HELMET, SlotType.GLOVES):
        return SlotEvaluationWeights(
            life_weight=1.2,
            res_weight=1.2,
            movement_speed_weight=0.0,
            defense_weight=0.5,
            attribute_weight=0.5,
        )
    # Weapons / off-hands
    return SlotEvaluationWeights(
        life_weight=0.8,
        res_weight=1.0,
        movement_speed_weight=0.0,
        defense_weight=0.2,
        attribute_weight=0.5,
    )


def compute_slot_score(candidate: ItemCandidate, slot: SlotType) -> float:
    weights = get_slot_weights(slot)
    contrib = build_item_contribution(candidate)

    score = 0.0
    score += contrib.life_delta * weights.life_weight
    score += (
        contrib.fire_res_delta
        + contrib.cold_res_delta
        + contrib.lightning_res_delta
        + contrib.chaos_res_delta
    ) * weights.res_weight
    score += contrib.movement_speed_delta * weights.movement_speed_weight
    score += (
        contrib.local_armour + contrib.local_evasion + contrib.local_energy_shield
    ) * weights.defense_weight
    score += (
        contrib.str_delta + contrib.dex_delta + contrib.int_delta
    ) * weights.attribute_weight

    return score
