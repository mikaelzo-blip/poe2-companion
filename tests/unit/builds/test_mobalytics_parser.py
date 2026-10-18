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


def test_plant_oracle_keeps_gem_progression_and_vendor_regex():
    prof, _, _ = _parse("plant-oracle-druid-leveling-build-guide")
    acts = {n.title: n.steps for n in prof.gem_notes}
    assert acts["Act 2"][0].startswith("When you get your first level 2 Support Gem")
    assert "Act 4 & Interludes" in acts
    assert prof.vendor_regex.startswith('"y: (r|m)"')


def test_guides_without_gem_notes_still_parse():
    prof, _, _ = _parse("fubgun-flameblast-oil-grenade")
    assert prof.gem_notes == [] and prof.vendor_regex is None


def test_plant_oracle_quest_rewards_and_passives():
    prof, _, _ = _parse("plant-oracle-druid-leveling-build-guide")
    medallion = next(q for q in prof.quest_rewards if q.quest == "Medallion")
    assert medallion.act == "Act 2" and "+1 Charm Slot" in medallion.reward
    assert {q.act for q in prof.quest_rewards} == {"Act 1", "Act 2", "Act 3", "Act 4", "Interlude"}
    notables = prof.stages[0].notables
    assert notables[0].name == "Guardian of the Wilds"
    assert ("Wildsurge Incantation", "KEY_STONE") in [(n.name, n.kind) for n in notables]
    assert notables[-1].kind == "ASCENDANCY_LARGE"
    assert any("Wasting Casts" in h for h in prof.tree_hints)


def test_quest_rewards_skip_entries_without_quest():
    data = _synth({})
    data["quest_rewards"] = [{"act": "Act 3", "quest": "Venom Draught", "reward": "25% increased Stun Threshold"},
                             {"act": "Act 3", "reward": "orphan"}]
    data["variants"][0]["notables"] = [{"name": "Radial Force"}, {"kind": "NOTABLE"}]
    prof, _, _ = parse_mobalytics_guide(data)
    assert [q.quest for q in prof.quest_rewards] == ["Venom Draught"]
    assert [(n.name, n.kind) for n in prof.stages[0].notables] == [("Radial Force", "NOTABLE")]


def test_source_url_must_be_http():
    data = json.loads((GUIDES / "plant-oracle-druid-leveling-build-guide.json").read_text(encoding="utf-8"))
    data["source_url"] = "javascript:alert(1)"
    assert parse_mobalytics_guide(data)[0].source_url is None
    data["source_url"] = "https://mobalytics.gg/poe-2/builds/x"
    assert parse_mobalytics_guide(data)[0].source_url == "https://mobalytics.gg/poe-2/builds/x"
