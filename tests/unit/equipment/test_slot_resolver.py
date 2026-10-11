from pathlib import Path

import pytest

from companion.builds.stages import resolve_stage
from companion.builds.store import load_guide
from companion.dashboard_api import import_guide_payload
from companion.equipment.parser import parse_item_text
from companion.equipment.slot_resolver import UI_SLOT_KEYS, canonical_slot, item_class_of, resolve_slots

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "guides"


def _item(item_class, base):
    return f"Item Class: {item_class}\nRarity: Rare\nDoom Name\n{base}\n--------\nRequires: Level 10\n--------\n+40 to maximum Life\n"


CROSSBOW = _item("Crossbows", "Makeshift Crossbow")
STAFF = _item("Staves", "Ashen Staff")
SCEPTRE = _item("Sceptres", "Rattling Sceptre")
RING = _item("Rings", "Iron Ring")
CHARM = _item("Charms", "Ruby Charm")


def _stage(tmp_path, slug, level):
    import_guide_payload({"text": (FIX / f"{slug}.json").read_text(encoding="utf-8")}, tmp_path)
    return resolve_stage(load_guide(tmp_path, slug), level)


@pytest.fixture
def fub60(tmp_path):
    return _stage(tmp_path, "fubgun-flameblast-oil-grenade", 60)


@pytest.fixture
def navira30(tmp_path):
    return _stage(tmp_path, "naviras-fracturing-varashta-league-starter", 30)


def test_fubgun_lvl60_crossbow_goes_to_set2(fub60):
    plans, reason = resolve_slots(parse_item_text(CROSSBOW), "Crossbow", fub60)
    assert [p.slot for p in plans] == ["Weapon 1 Swap"]
    assert plans[0].clear_slots == ("Weapon 2 Swap",)
    assert "Weapon Set 2" in reason


def test_fubgun_lvl60_staff_goes_to_set1(fub60):
    assert [p.slot for p in resolve_slots(parse_item_text(STAFF), "Staff", fub60)[0]] == ["Weapon 1"]


def test_one_hand_tries_both_hands(navira30):
    assert [p.slot for p in resolve_slots(parse_item_text(SCEPTRE), "Sceptre", navira30)[0]] == ["Weapon 1", "Weapon 2"]


def test_ring_tries_both_rings_and_lock_is_respected(fub60):
    ring = parse_item_text(RING)
    plans, reason = resolve_slots(ring, "Ring", fub60)
    assert [p.slot for p in plans] == ["Ring 1", "Ring 2"]
    assert reason == "Cincin: dicoba di Ring 1 dan Ring 2"
    assert [p.slot for p in resolve_slots(ring, "Ring", fub60, locked_slot="ring2")[0]] == ["Ring 2"]


def test_lock_mismatch_and_legacy_keys(fub60):
    with pytest.raises(ValueError, match="tidak cocok"):
        resolve_slots(parse_item_text(RING), "Ring", fub60, locked_slot="Helmet")
    assert canonical_slot("set2_main_hand") == "Weapon 1 Swap"
    assert canonical_slot("weapon_1_swap") == "Weapon 1 Swap"
    assert canonical_slot("Body Armour") == "Body Armour"
    assert UI_SLOT_KEYS["Weapon 2 Swap"] == "set2_off_hand"
    with pytest.raises(ValueError, match="Slot tidak dikenal: nope"):
        canonical_slot("nope")


def test_item_class_of_is_singular():
    assert item_class_of(CROSSBOW) == "Crossbow"
    assert item_class_of(STAFF) == "Staff"
    assert item_class_of("no class here") == ""


def test_non_equippable_item_raises(fub60):
    # parse_item_text falls back to a slot for charms, so the class check must catch it
    assert item_class_of(CHARM) == "Charm"
    with pytest.raises(ValueError, match="tidak bisa dipasang"):
        resolve_slots(parse_item_text(CHARM), item_class_of(CHARM), fub60)


def test_weapon_slot_lock_respects_guide_set(fub60):
    cb = parse_item_text(CROSSBOW)
    assert [p.slot for p in resolve_slots(cb, "Crossbow", fub60, locked_slot="set2_main_hand")[0]] == ["Weapon 1 Swap"]
    with pytest.raises(ValueError, match="tidak cocok"):
        resolve_slots(cb, "Crossbow", fub60, locked_slot="main_hand")
