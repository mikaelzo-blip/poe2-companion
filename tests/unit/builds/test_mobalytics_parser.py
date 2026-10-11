import json
from pathlib import Path

import pytest

from companion.builds.mobalytics import ITEM_CLASS_SLUG_LABELS, parse_mobalytics_guide
from companion.equipment.parser import parse_item_text
from companion.equipment.schema import SlotType

GUIDES = Path(__file__).resolve().parents[2] / "fixtures" / "guides"
NAMES = [p.stem for p in GUIDES.glob("*.json")]


def _family(slot):
    if slot.startswith("Weapon"):
        return {SlotType.MAIN_HAND, SlotType.OFF_HAND}
    if slot.startswith("Ring"):
        return {SlotType.RING_1, SlotType.RING_2}
    return {SlotType(slot.lower().replace(" ", "_"))}


def _parse(name):
    return parse_mobalytics_guide(json.loads((GUIDES / f"{name}.json").read_text(encoding="utf-8")))


def test_fubgun_crossbow_stage():
    prof, pob, _ = _parse("fubgun-flameblast-oil-grenade")
    st = next(s for s in prof.stages if s.title == "lvl 15-32")
    w = st.items["Weapon 1"]
    assert w.name == "Varnished Crossbow"
    assert "Physical Damage: 18-54" in w.raw_text
    assert parse_item_text(w.raw_text).slot == SlotType.MAIN_HAND
    assert prof.has_pob and pob and prof.pob_stage_id == prof.stages[-1].id
    assert st.main_skill


def test_fubgun_endgame_weapon_classes():
    prof, _, _ = _parse("fubgun-flameblast-oil-grenade")
    st = next(s for s in prof.stages if s.title == "Endgame")
    assert st.weapon_classes[1] == ["Staff"]
    assert "Crossbow" in st.weapon_classes[2]
    uniq = st.items["Body Armour"]
    assert uniq.is_unique and uniq.raw_text is None


def test_plant_oracle_no_pob():
    prof, pob, _ = _parse("plant-oracle-druid-leveling-build-guide")
    assert len(prof.stages) == 1 and not prof.has_pob and pob is None


@pytest.mark.parametrize("name", NAMES)
def test_all_non_unique_items_parse(name):
    prof, _, warnings = _parse(name)
    assert warnings == []
    for st in prof.stages:
        for it in st.items.values():
            assert it.item_class in ITEM_CLASS_SLUG_LABELS.values()
            if not it.is_unique:
                c = parse_item_text(it.raw_text)
                assert c.slot_conflict_topology.is_known, (it.slot, it.name)
                assert c.slot in _family(it.slot), (it.slot, it.name, c.slot)


def test_bad_format():
    with pytest.raises(ValueError):
        parse_mobalytics_guide({"format": "x"})


def _synth(items):
    return {"format": "poe2-companion-guide/1", "slug": "s", "name": "S",
            "variants": [{"id": "a", "title": "A", "items": items, "skills": []}]}


def test_synthetic_edge_cases():
    rare = {"name": "Iron Ring", "item_class": "ring", "is_unique": False, "stats": [], "mods": []}
    data = _synth({
        "leftRing": rare,
        "helmet": None,
        "belt": {"name": "Mageblood", "item_class": "belt", "is_unique": True},
        "charm1": rare,
        "flask1": rare,
        "mainHand.set1": {"name": "Odd Thing", "item_class": "war-fan", "is_unique": False,
                          "stats": [], "mods": []},
    })
    prof, pob, warnings = parse_mobalytics_guide(data)
    items = prof.stages[0].items
    assert set(items) == {"Ring 1", "Belt", "Weapon 1"}
    assert items["Belt"].is_unique and items["Belt"].raw_text is None
    assert items["Weapon 1"].item_class == "War Fan"
    assert pob is None and not prof.has_pob
    assert sum("charm1" in w or "flask1" in w for w in warnings) == 2
    assert any("war-fan" in w for w in warnings)
