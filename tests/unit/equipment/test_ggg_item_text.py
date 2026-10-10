import json
from pathlib import Path

import pytest

from companion.equipment.api_adapter import ggg_item_to_text
from companion.equipment.parser import parse_item_text
from companion.equipment.schema import SlotType


@pytest.fixture
def items():
    return json.loads((Path(__file__).parents[2] / "fixtures/ggg/items.json").read_text("utf-8"))


def test_rare_helm_text(items):
    text = ggg_item_to_text(items[0])
    assert text.splitlines()[:4] == ["Item Class: Helmets", "Rarity: Rare", "Plague Crest", "Face Mask"]
    assert "Evasion Rating: 37" in text and "Energy Shield: 18" in text
    assert "Requirements:" in text and "Level: 28" in text and "Dex: 10" in text
    assert "Item Level: 40" in text
    assert "+23% to Fire Resistance" in text and "[" not in text


def test_magic_ring_single_header_line(items):
    lines = ggg_item_to_text(items[1]).splitlines()
    assert lines[:3] == ["Item Class: Rings", "Rarity: Magic", "Smouldering Iron Ring of the Starfish"]
    assert "Adds 1 to 4 Physical Damage to Attacks (implicit)" in lines


def test_desecrated_and_multi_value_properties(items):
    assert "(desecrated)" in ggg_item_to_text(items[2])
    assert "Item Class: Staves" in ggg_item_to_text(items[2])
    assert "Armour: 120, 15" in ggg_item_to_text(items[3])


def test_text_round_trips_through_parser(items):
    parsed = parse_item_text(ggg_item_to_text(items[0]))
    assert parsed.base_type == "Face Mask" and parsed.slot == SlotType.HELMET


def test_minimal_payload_still_parseable():
    text = ggg_item_to_text({"name": "Doom Bite", "typeLine": "Iron Ring", "frameType": 2})
    assert text.splitlines()[:4] == ["Item Class: Iron Ring", "Rarity: Rare", "Doom Bite", "Iron Ring"]


def test_malformed_item_yields_warning_not_exception():
    from companion.equipment.api_adapter import GGGCharacterAPIAdapter

    payload = {"items": [
        {"inventoryId": "Boots", "name": "Good Boots", "typeLine": "Furtive Boots", "rarity": "Rare",
         "explicitMods": ["+50 to maximum Life"]},
        {"inventoryId": "Helm", "name": "Bad Helm", "typeLine": "Face Mask", "rarity": 5,
         "properties": [{"name": None, "values": []}], "explicitMods": [None, 3]},
    ]}
    loadout, _, warnings = GGGCharacterAPIAdapter.parse_character_payload(payload, "c1")
    assert loadout.get_slot(SlotType.BOOTS) is not None
    assert loadout.get_slot(SlotType.HELMET) is None
    assert any("Bad Helm" in w for w in warnings)
