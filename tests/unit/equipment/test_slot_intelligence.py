"""Unit tests for slot-specific evaluation weights and priorities."""

import pytest
from companion.equipment.schema import SlotType
from companion.equipment.slots import get_slot_weights, compute_slot_score
from companion.equipment.partial_projection import PartialLoadoutProjection, StatProjection
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


def test_boots_movement_speed_priority():
    weights = get_slot_weights(SlotType.BOOTS)
    assert weights.movement_speed_weight >= 3.0

    cand_ms = parse_item_text(BOOTS_WITH_MS, target_slot=SlotType.BOOTS)
    cand_no_ms = parse_item_text(BOOTS_NO_MS, target_slot=SlotType.BOOTS)

    # Candidate with movement speed gains high slot score
    score_ms = compute_slot_score(cand_ms, SlotType.BOOTS)
    score_no_ms = compute_slot_score(cand_no_ms, SlotType.BOOTS)

    # 15% MS at weight 3.0 gives +45 score
    assert score_ms > score_no_ms


def test_body_armour_local_defense_weight():
    weights = get_slot_weights(SlotType.BODY_ARMOUR)
    assert weights.defense_weight >= 1.0
    jewelry_weights = get_slot_weights(SlotType.RING_1)
    assert jewelry_weights.defense_weight == 0.0
