"""Unit tests for partial projection engine isolating known deltas from unknown absolutes."""

import pytest
from companion.state.provenance import VerificationState
from companion.equipment.schema import SlotType
from companion.equipment.parser import parse_item_text
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.partial_projection import (
    StatProjection,
    PartialLoadoutProjection,
    project_candidate_on_loadout,
)

BOOTS_OLD = """Item Class: Boots
Rarity: Rare
Old Boots
Furtive Boots
--------
Requirements:
Level: 45
--------
+40 to maximum Life
+30% to Fire Resistance
"""

BOOTS_NEW = """Item Class: Boots
Rarity: Rare
New Boots
Furtive Boots
--------
Armour: 250
--------
Requirements:
Level: 45
--------
+70 to maximum Life
+10% to Fire Resistance
+25% to Lightning Resistance
"""


def test_partial_projection_with_unknown_baseline():
    loadout = EquippedLoadout.create_draft(character_id="char_partial")
    old_boots = parse_item_text(BOOTS_OLD, target_slot=SlotType.BOOTS)
    loadout.set_slot(SlotType.BOOTS, old_boots)

    # Empty baseline where all stats are UNKNOWN
    baseline = CharacterStatBaseline.create_empty(character_id="char_partial", anchored_loadout_revision=1)

    cand = parse_item_text(BOOTS_NEW, target_slot=SlotType.BOOTS)
    proj = project_candidate_on_loadout(loadout, cand, SlotType.BOOTS, baseline=baseline)

    # Fire res delta is known: 10 - 30 = -20
    assert proj.fire_res.delta == -20.0
    assert proj.fire_res.is_delta_known is True
    # But projected absolute value is UNKNOWN!
    assert proj.fire_res.projected_absolute is None
    assert proj.fire_res.is_absolute_known is False

    # Life delta is known: 70 - 40 = +30
    assert proj.life.delta == 30.0
    assert proj.life.projected_absolute is None

    # Local armour is known on item (+250) but total character armour absolute is UNKNOWN
    assert proj.local_armour_delta == 250
    assert proj.armour.projected_absolute is None
