"""Unit tests for partial projection and resistance intelligence interactions."""

import pytest
from companion.equipment.schema import SlotType
from companion.equipment.parser import parse_item_text
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.partial_projection import project_candidate_on_loadout

RING_OLD = """Item Class: Rings
Rarity: Rare
Old Topaz Ring
Topaz Ring
--------
Requirements:
Level: 40
--------
+35% to Lightning Resistance
"""

RING_NEW = """Item Class: Rings
Rarity: Rare
New Coral Ring
Coral Ring
--------
Requirements:
Level: 40
--------
+15% to Lightning Resistance
+40 to maximum Life
"""


def test_overcap_buffer_absorbs_drop_in_partial_projection():
    loadout = EquippedLoadout.create_draft(character_id="char_res")
    old_ring = parse_item_text(RING_OLD, target_slot=SlotType.RING_1)
    loadout.set_slot(SlotType.RING_1, old_ring)

    # Raw lightning res is 105% (30% overcap buffer)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base1",
        character_id="char_res",
        anchored_loadout_revision=1,
        lightning_res=75,
        lightning_raw=105,
        max_lightning_res=75,
    )

    new_ring = parse_item_text(RING_NEW, target_slot=SlotType.RING_1)
    proj = project_candidate_on_loadout(loadout, new_ring, SlotType.RING_1, baseline=baseline)

    # Net lightning delta is -20
    assert proj.lightning_res.delta == -20.0
    # Overcap buffer absorbed the loss: new raw 85, new effective still 75!
    assert proj.lightning_res.projected_absolute == 75
    assert proj.lightning_res.projected_raw == 85
    assert proj.lightning_res.projected_overcap == 10


def test_missing_defensive_baseline_does_not_block_res_or_attr_evaluation():
    loadout = EquippedLoadout.create_draft(character_id="char_res2")
    old_ring = parse_item_text(RING_OLD, target_slot=SlotType.RING_1)
    loadout.set_slot(SlotType.RING_1, old_ring)

    # Baseline only has attributes and raw res; life, armour, evasion are UNKNOWN
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base2",
        character_id="char_res2",
        anchored_loadout_revision=1,
        strength=100,
        lightning_res=75,
        lightning_raw=90,
    )

    new_ring = parse_item_text(RING_NEW, target_slot=SlotType.RING_1)
    proj = project_candidate_on_loadout(loadout, new_ring, SlotType.RING_1, baseline=baseline)

    # Lightning res projected fine
    assert proj.lightning_res.delta == -20.0
    assert proj.lightning_res.projected_absolute == 70  # 90 - 20 = 70
    # Life delta is known (+40) but projected absolute life is None (UNKNOWN)
    assert proj.life.delta == 40.0
    assert proj.life.projected_absolute is None
