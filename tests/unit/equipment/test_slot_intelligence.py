"""Unit tests for slot-specific contextual priorities and profiles."""

import pytest
from companion.equipment.schema import SlotType
from companion.equipment.slots import (
    SlotPriorityCategory,
    SlotContextualProfile,
    get_slot_contextual_profile,
    get_slot_weights,
    compute_slot_score,
)
from companion.equipment.contribution import build_item_contribution
from companion.equipment.parser import parse_item_text

BOOTS_WITH_MS = """Item Class: Boots
Rarity: Rare
Sprint Treads
Furtive Boots
--------
Requirements:
Level: 45
--------
+30 to maximum Life
+15% increased Movement Speed
"""

BOOTS_NO_MS = """Item Class: Boots
Rarity: Rare
Heavy Treads
Furtive Boots
--------
Requirements:
Level: 45
--------
+40 to maximum Life
+25% to Fire Resistance
"""


def test_boots_movement_speed_contextual_priority():
    profile = get_slot_contextual_profile(SlotType.BOOTS)
    assert profile.movement_speed_priority == SlotPriorityCategory.PRIMARY
    assert "movement_speed" in profile.primary_properties
    assert profile.local_defense_priority == SlotPriorityCategory.TERTIARY

    cand_ms = parse_item_text(BOOTS_WITH_MS, target_slot=SlotType.BOOTS)
    contrib_ms = build_item_contribution(cand_ms)
    assert contrib_ms.movement_speed_delta == 15.0


def test_body_armour_local_defense_contextual_priority():
    profile = get_slot_contextual_profile(SlotType.BODY_ARMOUR)
    assert profile.local_defense_priority == SlotPriorityCategory.PRIMARY
    assert "local_defenses" in profile.primary_properties
    assert profile.movement_speed_priority == SlotPriorityCategory.TERTIARY

    ring_profile = get_slot_contextual_profile(SlotType.RING_1)
    assert ring_profile.local_defense_priority == SlotPriorityCategory.TERTIARY
    assert ring_profile.movement_speed_priority == SlotPriorityCategory.TERTIARY


def test_jewelry_contextual_profile():
    for slot in (SlotType.RING_1, SlotType.RING_2, SlotType.AMULET, SlotType.BELT):
        profile = get_slot_contextual_profile(slot)
        assert "resistances" in profile.primary_properties
        assert "life" in profile.primary_properties
        assert "attributes" in profile.primary_properties
        assert profile.local_defense_priority == SlotPriorityCategory.TERTIARY
        assert profile.movement_speed_priority == SlotPriorityCategory.TERTIARY


def test_hybrid_defense_slots_contextual_profile():
    for slot in (SlotType.HELMET, SlotType.GLOVES):
        profile = get_slot_contextual_profile(slot)
        assert "life" in profile.primary_properties
        assert "resistances" in profile.primary_properties
        assert "local_defenses" in profile.primary_properties
        assert profile.local_defense_priority == SlotPriorityCategory.SECONDARY
        assert profile.movement_speed_priority == SlotPriorityCategory.TERTIARY


def test_weapon_contextual_profile():
    profile = get_slot_contextual_profile(SlotType.MAIN_HAND)
    assert "offensive_scaling" in profile.primary_properties
    assert "life" in profile.primary_properties
    assert profile.local_defense_priority == SlotPriorityCategory.TERTIARY
    assert profile.movement_speed_priority == SlotPriorityCategory.TERTIARY


def test_deprecated_compute_slot_score_emits_warning():
    cand_ms = parse_item_text(BOOTS_WITH_MS, target_slot=SlotType.BOOTS)
    with pytest.deprecated_call():
        score = compute_slot_score(cand_ms, SlotType.BOOTS)
    assert score > 0.0

    with pytest.deprecated_call():
        weights = get_slot_weights(SlotType.BOOTS)
    assert weights.life_weight > 0.0
