import base64
import json
import zlib
from pathlib import Path

import pytest

from companion.builds.pob_code import decode_share_code, fetch_pobb_code, parse_pob_xml
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


def test_roundtrip_and_parse():
    assert decode_share_code("  " + _code(XML) + "\n") == XML
    p = parse_pob_xml(XML, "Test")
    assert [(s.min_level, s.max_level) for s in p.stages] == [(1, 40), (41, 100)]
    assert p.has_pob and p.pob_stage_id == "2"
    assert p.stages[1].main_skill == "Rain of Arrows"
    h = p.stages[0].items["Helmet"]
    assert h.name == "Doom Crown" and "Item Class: Helmets" in h.raw_text
    assert "15% increased Armour" in h.raw_text
    assert set(p.stages[0].items) == {"Helmet"}
    assert p.stages[1].items["Weapon 1"].item_class == "Crossbows"


def test_invalid_code():
    with pytest.raises(ValueError, match="Kode PoB2 tidak valid"):
        decode_share_code("not a code")


def test_fetch_pobb():
    seen = {}

    class R:
        def read(self):
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


@pytest.mark.parametrize("u", ["https://evil.com/x", "http://pobb.in/abc", "https://pobb.in/", "https://pobb.in/a/b"])
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
