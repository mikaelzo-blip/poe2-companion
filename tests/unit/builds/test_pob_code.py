import base64
import json
import zlib
from pathlib import Path

import pytest

from companion.builds.pob_code import active_item_set_title, decode_share_code, fetch_pobb_code, parse_pob_xml
from companion.equipment.parser import parse_item_text

HELMET = """Rarity: RARE
Doom Crown
Iron Crown
Item Level: 80
LevelReq: 0
Implicits: 0
{range:0.5}(10-20)% increased Armour
+30 to maximum Life"""
CROSSBOW = """Rarity: NORMAL
Tense Crossbow
Implicits: 0"""

XML = f"""<PathOfBuilding2>
<Build level="90" mainSocketGroup="2"/>
<Skills activeSkillSet="1"><SkillSet id="1">
<Skill><Gem nameSpec="Frost Bolt"/></Skill>
<Skill><Gem nameSpec="Rain of Arrows"/><Gem nameSpec="Support"/></Skill>
</SkillSet></Skills>
<Items activeItemSet="2">
<Item id="1">
  {HELMET}
</Item>
<Item id="2">
  {CROSSBOW}
</Item>
<ItemSet id="1" title="Leveling lvl 1-40"><Slot name="Helmet" itemId="1"/><Slot name="Flask 1" itemId="2"/></ItemSet>
<ItemSet id="2" title="Endgame"><Slot name="Helmet" itemId="1"/><Slot name="Weapon 1" itemId="2"/><Slot name="Belt" itemId="0"/></ItemSet>
</Items></PathOfBuilding2>"""


def _code(xml):
    return base64.urlsafe_b64encode(zlib.compress(xml.encode())).decode().rstrip("=")


def test_active_item_set_title():
    xml = (
        '<PathOfBuilding2><Items activeItemSet="2">'
        '<ItemSet id="1" title="Leveling"/>'
        '<ItemSet id="2" title="Late Endgame"/>'
        '</Items></PathOfBuilding2>'
    )
    assert active_item_set_title(xml) == "Late Endgame"
    assert active_item_set_title('<PathOfBuilding2><Items><ItemSet id="1" title="A"/></Items></PathOfBuilding2>') is None
    assert active_item_set_title('<PathOfBuilding2><Items activeItemSet="2"><ItemSet id="1" title="A"/></Items></PathOfBuilding2>') is None
    assert active_item_set_title("<invalid>") is None


def test_roundtrip_and_parse():
    assert decode_share_code("  " + _code(XML) + "\n") == XML
    p = parse_pob_xml(XML, "Test")
    assert [(s.min_level, s.max_level) for s in p.stages] == [(1, 64), (65, 100)]
    assert p.has_pob and p.pob_stage_id == "2"
    assert p.stages[1].main_skill == "Rain of Arrows"
    h = p.stages[0].items["Helmet"]
    assert h.name == "Iron Crown" and h.item_class == "Helmet" and "Item Class: Helmets" in h.raw_text
    assert "+30 to maximum Life" in h.mods
    assert "15% increased Armour" in h.raw_text
    assert set(p.stages[0].items) == {"Helmet"}
    assert p.stages[1].items["Weapon 1"].item_class == "Crossbow"


def test_invalid_code():
    with pytest.raises(ValueError, match="Kode PoB2 tidak valid"):
        decode_share_code("not a code")


def test_fetch_pobb():
    seen = {}

    class R:
        def read(self, n=None):
            return b" abc \n"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    def opener(url, timeout=None):
        seen["url"], seen["t"] = url, timeout
        return R()

    assert fetch_pobb_code("https://pobb.in/abc", opener=opener) == "abc"
    assert seen == {"url": "https://pobb.in/abc/raw", "t": 15}
    fetch_pobb_code("https://pobb.in/abc/raw", opener=opener)
    assert seen["url"] == "https://pobb.in/abc/raw"


@pytest.mark.parametrize("u", ["https://evil.com/x", "http://pobb.in/abc", "https://pobb.in/", "https://pobb.in/a/b",
                               "https://pobb.in.evil.com/x", "https://pobb.in@evil.com/x", "https://evil.com/pobb.in/x"])
def test_fetch_rejects(u):
    with pytest.raises(ValueError):
        fetch_pobb_code(u)


def test_real_fixture():
    f = Path(__file__).resolve().parents[2] / "fixtures" / "guides" / "fubgun-flameblast-oil-grenade.json"
    code = json.loads(f.read_text(encoding="utf-8"))["pob_code"]
    p = parse_pob_xml(decode_share_code(code), "Fubgun")
    assert len(p.stages) >= 1
    assert p.pob_stage_id in {s.id for s in p.stages}
    n = 0
    for s in p.stages:
        for it in s.items.values():
            if it.raw_text:
                parse_item_text(it.raw_text)
                n += 1
    assert n > 0


SK_XML = """<PathOfBuilding2><Build mainSocketGroup="1"/>
<Skills activeSkillSet="2">
<SkillSet id="1" title="Endgame"><Skill><Gem nameSpec="Late Skill"/></Skill></SkillSet>
<SkillSet id="2" title="Other"><Skill><Gem nameSpec="Early Skill"/></Skill></SkillSet>
</Skills>
<Items activeItemSet="1">
<ItemSet id="1" title="Leveling"/><ItemSet id="2" title="Endgame"/>
</Items></PathOfBuilding2>"""


def test_main_skill_only_for_active_skill_set():
    # mainSocketGroup indexes the active SkillSet ("Other", id 2) only; other sets have no main-skill marker.
    p = parse_pob_xml(SK_XML, "S")
    # "Leveling" -> position 0 -> "Endgame" set (inactive); "Endgame" -> title match (inactive)
    assert [s.main_skill for s in p.stages] == [None, None]
    p = parse_pob_xml(SK_XML.replace('title="Endgame"><Skill', 'title="X"><Skill').replace('title="Other"', 'title="Y"'), "S")
    assert [s.main_skill for s in p.stages] == [None, "Early Skill"]  # position match hits the active set
    p = parse_pob_xml(SK_XML.replace('<ItemSet id="1" title="Leveling"/><ItemSet id="2" title="Endgame"/>',
                                     '<ItemSet id="1" title="Z"/><ItemSet id="2" title="Other"/>'), "S")
    assert [s.main_skill for s in p.stages] == [None, "Early Skill"]  # title match hits the active set


def test_main_skill_empty_matched_set_does_not_borrow_another():
    xml = SK_XML.replace('<SkillSet id="2" title="Other"><Skill><Gem nameSpec="Early Skill"/></Skill></SkillSet>',
                         '<SkillSet id="2" title="Other"></SkillSet>')
    xml = xml.replace('<ItemSet id="2" title="Endgame"/>', '<ItemSet id="2" title="Other"/>')
    assert parse_pob_xml(xml, "S").stages[1].main_skill is None


def test_conversion_failure_falls_back(caplog):
    bad = "Rarity: RARE\nMy Thing\nNo Such Base\nImplicits: 0"
    xml = f'<P><Items activeItemSet="1"><Item id="1">{bad}</Item><ItemSet id="1"><Slot name="Belt" itemId="1"/></ItemSet></Items></P>'
    it = parse_pob_xml(xml, "B").stages[0].items["Belt"]
    assert it.name == "My Thing" and it.raw_text is None


def test_unconvertible_item_emits_warning_and_sets_raw_text_none():
    bad = "Rarity: RARE\nMy Thing\nNo Such Base\nImplicits: 0"
    xml = (
        '<PathOfBuilding2><Items activeItemSet="1">'
        f'<Item id="1">{HELMET}</Item>'
        f'<Item id="2">{bad}</Item>'
        '<ItemSet id="1" title="Endgame">'
        '<Slot name="Helmet" itemId="1"/>'
        '<Slot name="Belt" itemId="2"/>'
        '</ItemSet>'
        '</Items></PathOfBuilding2>'
    )
    warnings: list[str] = []
    profile = parse_pob_xml(xml, "Test", warnings)
    stage = profile.stages[0]

    bad_item = stage.items["Belt"]
    assert bad_item.raw_text is None
    assert bad_item.item_class == ""
    assert len(warnings) == 1
    assert "Belt" in warnings[0]

    good_item = stage.items["Helmet"]
    assert good_item.raw_text is not None
    assert "Item Class: Helmets" in good_item.raw_text


def test_decompression_cap():
    big = base64.urlsafe_b64encode(zlib.compress(b"a" * 21_000_000)).decode()
    with pytest.raises(ValueError, match="Kode PoB2 tidak valid"):
        decode_share_code(big)


def test_real_fixture_matches_mobalytics_contract():
    f = Path(__file__).resolve().parents[2] / "fixtures" / "guides" / "fubgun-flameblast-oil-grenade.json"
    p = parse_pob_xml(decode_share_code(json.loads(f.read_text(encoding="utf-8"))["pob_code"]), "Fubgun")
    items = [it for s in p.stages for it in s.items.values()]
    assert not {it.item_class for it in items} & {"Crossbows", "Staves", "Foci", "Helmets"}
    assert any(it.item_class == "Crossbow" for it in items)
    rare = next(it for it in items if not it.is_unique)
    assert rare.name == rare.raw_text.splitlines()[3] and rare.mods
    assert any(s.weapon_classes.get(1) for s in p.stages)
    assert any(s.weapon_classes.get(2) == ["Crossbow"] for s in p.stages)
