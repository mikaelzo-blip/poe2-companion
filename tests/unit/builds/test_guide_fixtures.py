import json
from pathlib import Path

import pytest

GUIDES = Path(__file__).resolve().parents[2] / "fixtures" / "guides"
NAMES = [
    "fubgun-flameblast-oil-grenade",
    "naviras-fracturing-varashta-league-starter",
    "plant-oracle-druid-leveling-build-guide",
]


def _load(name):
    return json.loads((GUIDES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", NAMES)
def test_fixture_shape_and_trimmed(name):
    raw = (GUIDES / f"{name}.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data["format"] == "poe2-companion-guide/1"
    assert data["slug"] == name
    assert len(data["variants"]) >= 1
    assert "iconURL" not in raw
    assert "poe2TradeRequest" not in raw


def test_fubgun_variants_and_pob():
    data = _load("fubgun-flameblast-oil-grenade")
    assert [v["title"] for v in data["variants"]] == [
        "lvl 1-14", "lvl 15-32", "lvl 33-51", "lvl 52 Swap", "lvl 53-68",
        "lvl 85", "Endgame", "Mageblood", "DoT Cap",
    ]
    assert data["pob_code"]


def test_plant_oracle_has_no_pob():
    assert _load("plant-oracle-druid-leveling-build-guide")["pob_code"] is None
