import json
from pathlib import Path

import pytest

from companion.equipment.parser import parse_item_text
from companion.equipment.pob_item_text import PobItemTextError, pob_item_to_clipboard
from companion.equipment.schema import NormalizedModifierType, SlotType

# Real engine output (get_equipped after import_character); see tests/fixtures/pob.
EQUIPPED = json.loads((Path(__file__).parents[2] / "fixtures" / "pob" / "get_equipped.json").read_text(encoding="utf-8"))
UNKNOWN = NormalizedModifierType.UNKNOWN_MODIFIER


def _item(slot, target=None):
    return parse_item_text(pob_item_to_clipboard(EQUIPPED[slot]["raw"]), target_slot=target)


def test_helmet_parses_with_known_mods_and_local_defenses():
    item = _item("Helmet")
    assert item.name == "Plague Crest" and item.base_type == "Face Mask" and item.slot == SlotType.HELMET
    assert (item.local_evasion, item.local_energy_shield, item.required_level, item.item_level) == (37, 18, 28, 40)
    types = {m.modifier_type for m in item.modifiers}
    assert {NormalizedModifierType.MAXIMUM_LIFE, NormalizedModifierType.FIRE_RESISTANCE,
            NormalizedModifierType.LIGHTNING_RESISTANCE} <= types
    assert sum(m.modifier_type != UNKNOWN for m in item.modifiers) >= 4


def test_implicits_are_marked_and_magic_name_resolves_base():
    amulet = _item("Amulet")
    assert [m.is_implicit for m in amulet.modifiers].count(True) == 1
    ring = _item("Ring 2", SlotType.RING_2)
    assert ring.slot == SlotType.RING_2 and ring.rarity == "magic"
    assert sum(m.is_implicit for m in ring.modifiers) == 1


def test_weapon_class_and_tags_and_status_lines():
    staff = _item("Weapon 1")
    assert staff.base_type == "Pyrophyte Staff" and staff.slot == SlotType.MAIN_HAND
    boots_text = pob_item_to_clipboard(EQUIPPED["Boots"]["raw"])
    assert "{" not in boots_text and "+5% to Cold Resistance (enchant)" in boots_text
    assert "+12 to Dexterity (desecrated)" in boots_text and boots_text.rstrip().endswith("Corrupted")
    assert "Evasion Rating: 65" in boots_text


def test_range_and_tag_prefixes_are_resolved():
    raw = ("Rarity: RARE\nX\nIron Ring\nItem Level: 5\nLevelReq: 1\nImplicits: 0\n"
           "{tags:life}{range:0.5}+(10-20) to maximum Life\n{crafted}+7% to Cold Resistance")
    text = pob_item_to_clipboard(raw)
    assert "+15 to maximum Life" in text and "+7% to Cold Resistance" in text and "{" not in text


@pytest.mark.parametrize("bad", ["", "garbage", "Rarity: RARE\nOnly Name", "Item Class: Rings\nRarity: Rare\nA\nB",
                                 "Rarity: RARE\nA\nNo Such Base\nImplicits: 0"])
def test_unconvertible_input_raises(bad):
    with pytest.raises(PobItemTextError):
        pob_item_to_clipboard(bad)


def test_unknown_property_line_is_ignored():
    raw = ("Rarity: RARE\nRune Grip\nIron Gauntlets\nItem Level: 5\nLevelReq: 1\n"
           "Runic Ward: 62\nImplicits: 0\n+30 to maximum Life")
    text = pob_item_to_clipboard(raw)
    assert "+30 to maximum Life" in text and "Runic Ward" not in text
