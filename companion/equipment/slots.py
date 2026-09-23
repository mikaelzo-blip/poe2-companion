"""Slot-specific contextual priorities and evaluation rules."""

from __future__ import annotations

import warnings
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from companion.equipment.contribution import build_item_contribution
from companion.equipment.schema import ItemCandidate, SlotType


class SlotPriorityCategory(str, Enum):
    MANDATORY = "MANDATORY"
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    TERTIARY = "TERTIARY"


class SlotContextualProfile(BaseModel):
    """Contextual priorities and property rules for a specific equipment slot."""

    model_config = ConfigDict(frozen=True)

    slot: SlotType
    primary_properties: list[str] = Field(default_factory=list)
    secondary_properties: list[str] = Field(default_factory=list)
    slot_role: str = ""
    movement_speed_priority: SlotPriorityCategory = SlotPriorityCategory.TERTIARY
    local_defense_priority: SlotPriorityCategory = SlotPriorityCategory.TERTIARY


def get_slot_contextual_profile(slot: SlotType) -> SlotContextualProfile:
    """Returns contextual slot priority profile for evaluating slot properties."""
    if slot == SlotType.BOOTS:
        return SlotContextualProfile(
            slot=slot,
            primary_properties=["movement_speed", "life", "resistances"],
            secondary_properties=["attributes"],
            slot_role="Movement speed critical slot with defensive baseline support.",
            movement_speed_priority=SlotPriorityCategory.PRIMARY,
            local_defense_priority=SlotPriorityCategory.TERTIARY,
        )
    if slot == SlotType.BODY_ARMOUR:
        return SlotContextualProfile(
            slot=slot,
            primary_properties=["local_defenses", "life"],
            secondary_properties=["resistances", "attributes"],
            slot_role="Primary local defense and effective life anchoring slot.",
            movement_speed_priority=SlotPriorityCategory.TERTIARY,
            local_defense_priority=SlotPriorityCategory.PRIMARY,
        )
    if slot in (SlotType.RING_1, SlotType.RING_2, SlotType.AMULET, SlotType.BELT):
        return SlotContextualProfile(
            slot=slot,
            primary_properties=["resistances", "life", "attributes"],
            secondary_properties=[],
            slot_role="Jewelry flexibility and resistance/attribute cap solver slot.",
            movement_speed_priority=SlotPriorityCategory.TERTIARY,
            local_defense_priority=SlotPriorityCategory.TERTIARY,
        )
    if slot in (SlotType.HELMET, SlotType.GLOVES):
        return SlotContextualProfile(
            slot=slot,
            primary_properties=["life", "resistances", "local_defenses"],
            secondary_properties=["attributes"],
            slot_role="Hybrid defensive and resistance coverage slot.",
            movement_speed_priority=SlotPriorityCategory.TERTIARY,
            local_defense_priority=SlotPriorityCategory.SECONDARY,
        )
    # Weapons / Off-hands
    return SlotContextualProfile(
        slot=slot,
        primary_properties=["offensive_scaling", "life"],
        secondary_properties=["resistances", "attributes"],
        slot_role="Offensive scaling anchor with secondary utility.",
        movement_speed_priority=SlotPriorityCategory.TERTIARY,
        local_defense_priority=SlotPriorityCategory.TERTIARY,
    )


# ---------------------------------------------------------
# Deprecated scalar scoring constructs
# Kept for backward compatibility until Task 6 refactors engine.py
# ---------------------------------------------------------

class SlotEvaluationWeights(BaseModel):
    model_config = ConfigDict(frozen=True)

    life_weight: float = 1.0
    res_weight: float = 1.5
    movement_speed_weight: float = 1.0
    defense_weight: float = 0.05
    attribute_weight: float = 0.5


def get_slot_weights(slot: SlotType) -> SlotEvaluationWeights:
    """[DEPRECATED] Returns scalar weights for slot evaluation."""
    warnings.warn(
        "get_slot_weights is deprecated; use get_slot_contextual_profile instead.",
        DeprecationWarning,
        stacklevel=2,
    )
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
    return SlotEvaluationWeights(
        life_weight=0.8,
        res_weight=1.0,
        movement_speed_weight=0.0,
        defense_weight=0.2,
        attribute_weight=0.5,
    )


def compute_slot_score(candidate: ItemCandidate, slot: SlotType) -> float:
    """[DEPRECATED] Scalar score summation over item candidate."""
    warnings.warn(
        "compute_slot_score is deprecated; use multidimensional contextual comparison instead.",
        DeprecationWarning,
        stacklevel=2,
    )
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
