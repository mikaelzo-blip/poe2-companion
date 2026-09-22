"""Unit tests for tooltip parsing and multi-capture stability gate."""

import pytest

from companion.gear.schema import ItemRarity, ItemSlot
from companion.gear.tooltip import parse_item_tooltip, verify_tooltip_stability
from companion.state.provenance import VerificationState


SAMPLE_TOOLTIP_1 = """
Rarity: Rare
Storm Tread
Iron Greaves
--------
Requires Level 45, 52 Str
--------
Sockets: S S
--------
Item Level: 68
--------
+45 to Maximum Life
+25% to Cold Resistance
30% increased Movement Speed
"""

SAMPLE_TOOLTIP_2 = """
Rarity: Unique
Kaom's Primacy
Karui Chopper
--------
Two Handed Axe
Requires Level 58, 120 Str
--------
+100 to Maximum Life
Adds 50 to 90 Physical Damage
"""

SAMPLE_TOOLTIP_DIFFERENT = """
Rarity: Rare
Storm Tread
Iron Greaves
--------
Requires Level 45, 52 Str
--------
+55 to Maximum Life
+25% to Cold Resistance
"""


def test_parse_item_tooltip_rare() -> None:
    item = parse_item_tooltip(SAMPLE_TOOLTIP_1, slot=ItemSlot.BOOTS)
    assert item.slot == ItemSlot.BOOTS
    assert item.rarity == ItemRarity.RARE
    assert item.name == "Storm Tread"
    assert item.base_type == "Iron Greaves"
    assert item.level_req == 45
    assert item.required_str == 52
    assert item.required_dex == 0
    assert item.required_int == 0
    assert item.sockets == 2
    assert len(item.explicit_mods) == 3
    assert item.item_hash is not None
    assert len(item.item_hash) == 64


def test_parse_item_tooltip_unique() -> None:
    item = parse_item_tooltip(SAMPLE_TOOLTIP_2, slot=ItemSlot.MAIN_HAND)
    assert item.slot == ItemSlot.MAIN_HAND
    assert item.rarity == ItemRarity.UNIQUE
    assert item.name == "Kaom's Primacy"
    assert item.base_type == "Karui Chopper"
    assert item.level_req == 58
    assert item.required_str == 120
    assert len(item.explicit_mods) == 2


def test_verify_tooltip_stability_empty_and_single() -> None:
    item, state = verify_tooltip_stability([], slot=ItemSlot.BOOTS)
    assert item is None
    assert state == VerificationState.UNKNOWN

    item_single, state_single = verify_tooltip_stability([SAMPLE_TOOLTIP_1], slot=ItemSlot.BOOTS)
    assert item_single is not None
    assert state_single == VerificationState.SINGLE_SOURCE


def test_verify_tooltip_stability_corroborated_and_conflicting() -> None:
    # 2 identical captures -> VERIFIED
    item_v, state_v = verify_tooltip_stability([SAMPLE_TOOLTIP_1, SAMPLE_TOOLTIP_1], slot=ItemSlot.BOOTS)
    assert item_v is not None
    assert state_v == VerificationState.VERIFIED
    assert item_v.verification == VerificationState.VERIFIED

    # 2 differing captures -> CONFLICTING
    item_c, state_c = verify_tooltip_stability([SAMPLE_TOOLTIP_1, SAMPLE_TOOLTIP_DIFFERENT], slot=ItemSlot.BOOTS)
    assert item_c is not None
    assert state_c == VerificationState.CONFLICTING
