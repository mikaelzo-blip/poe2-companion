import json
from pathlib import Path

import pytest

from companion.builds.mobalytics import ITEM_CLASS_SLUG_LABELS, parse_mobalytics_guide
from companion.equipment.parser import parse_item_text
from companion.equipment.schema import SlotType

GUIDES = Path(__file__).resolve().parents[2] / "fixtures" / "guides"
NAMES = [p.stem for p in GUIDES.glob("*.json")]


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
                parse_item_text(it.raw_text)


def test_bad_format():
    with pytest.raises(ValueError):
        parse_mobalytics_guide({"format": "x"})
