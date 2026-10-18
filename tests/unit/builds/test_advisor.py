"""Guide-driven objectives: resists per act, gem steps, weighted slot gaps, vendor regex, PoB slot ranking."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from companion.builds import advisor
from companion.builds.guide import GemNote, GuideProfile, GuideStage, StageItem
from companion.builds.store import save_guide, set_assignment
from companion.equipment.baseline import BaselineSource, CharacterFact, CharacterStatBaseline
from companion.equipment.baseline_cli import save_baseline

WAND = StageItem(slot="Weapon 1", name="Bone Wand", item_class="Wand", raw_text="Rarity: Rare\nGuide\nBone Wand",
                 mods=["+5 to Level of all Physical Spell Skills", "75% increased Spell Damage", "29% increased Cast Speed"])
BELT = StageItem(slot="Belt", name="Plate Belt", item_class="Belt", raw_text="Rarity: Rare\nGuide\nPlate Belt",
                 mods=["+100 to maximum Life", "+31% to Fire Resistance", "+31% to Cold Resistance"])
REGEX = '"y: (r|m)" "ph.*da|st spe" "s: (am|ri)"'


def _profile() -> GuideProfile:
    return GuideProfile(
        slug="plant", name="Plant", imported_at="2026-01-01T00:00:00Z", vendor_regex=REGEX,
        stages=[GuideStage(id="s", title="Leveling", items={"Weapon 1": WAND, "Belt": BELT}, main_skill="Entangle")],
        gem_notes=[GemNote(title="Act 1", steps=["Cut Entangle"]), GemNote(title="Act 2", steps=["Zenith I", "Storm Rune"]),
                   GemNote(title="Act 4 & Interludes", steps=["Cast on Critical"])],
    )


def _baseline(res: tuple[int, int, int], penalty: int | None, source=BaselineSource.DERIVED_CALCULATION):
    b = CharacterStatBaseline.create_empty("P")
    for el, v in zip(("fire", "cold", "lightning"), res):
        setattr(b, f"raw_{el}_res", CharacterFact[int].create(v, source=source))
    b.resist_penalty = penalty
    return b


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    save_guide(tmp_path, _profile())
    set_assignment(tmp_path, "P", "plant", None)
    (tmp_path / "characters").mkdir()
    (tmp_path / "characters" / "P.json").write_text(
        json.dumps({"level": {"value": 23}, "current_zone": {"value": "The Titan Grotto"}}), encoding="utf-8")
    gear = {"Weapon 1": "Item Class: Wands\nRarity: Rare\nX\nBone Wand\n--------\nItem Level: 20\n--------\n"
                        "40% increased Spell Damage\n10% increased Cast Speed",
            "Belt": "Item Class: Belts\nRarity: Rare\nY\nRawhide Belt\n--------\nItem Level: 20\n--------\n"
                    "+39 to maximum Mana\n+7% to all Elemental Resistances"}
    monkeypatch.setattr(advisor, "get_current_raw", lambda rt, cid, slot, pob=None: gear.get(slot, ""))
    return tmp_path


def test_resists_reproject_from_the_recorded_penalty():
    pob_endgame = _baseline((-12, -10, -5), None)  # unrecorded penalty = PoB's -60
    assert advisor.resist_by_act(pob_endgame, 2, current_act=2) == {"fire": 38, "cold": 40, "lightning": 45}
    assert advisor.resist_by_act(_baseline((38, 40, 45), -10), 3, current_act=2) == {
        "fire": 28, "cold": 30, "lightning": 35}
    in_game = _baseline((38, 40, 45), -60, source=BaselineSource.MANUAL_USER_INPUT)  # carries the current act's
    assert advisor.resist_by_act(in_game, 3, current_act=2) == {"fire": 28, "cold": 30, "lightning": 35}
    assert advisor.resist_by_act(_baseline((90, 90, 90), 0), 1, current_act=1)["fire"] == 75  # capped


def test_slot_gaps_weight_skill_levels_and_count_all_resist(runtime):
    gaps = {slot: (round(gap, 2), missing) for slot, gap, missing in
            advisor.slot_gaps(runtime, "P", _profile().stages[0])}
    assert gaps["Weapon 1"] == (0.6, ["+5 to Level of all Physical Spell Skills"])  # 3 of 5 weight
    assert gaps["Belt"] == (0.33, ["+100 to maximum Life"])  # all-res covers fire and cold


def test_vendor_regex_adds_resist_to_the_mod_group():
    p = _profile()
    assert advisor.vendor_regex(p, True) == '"y: (r|m)" "ph.*da|st spe|resi" "s: (am|ri)"'
    assert advisor.vendor_regex(p, False) == REGEX


def test_guide_objectives_for_the_current_act(runtime):
    save_baseline(runtime, _baseline((38, 40, 45), -10))
    out = advisor.guide_objectives(runtime, "P")
    ids = [o["id"] for o in out["all_objectives"]]
    assert out["act"] == 2 and out["primary_objective"]["id"] == "guide:resist"
    assert ids == ["guide:resist", "guide:gems:2", "guide:slot:Weapon 1", "guide:regex"]
    gems = next(o for o in out["all_objectives"] if o["id"] == "guide:gems:2")
    assert gems["action"] == "• Zenith I\n• Storm Rune"
    assert "28%/30%/35%" in out["primary_objective"]["rationale"]
    assert out["all_objectives"][-1]["action"].endswith('|resi" "s: (am|ri)"')


def test_interlude_uses_the_act_4_and_interludes_notes(runtime):
    assert advisor._gem_objective(_profile(), 6)["title"] == "Gem Act 4 & Interludes (guide)"


def test_no_guide_means_no_guide_objectives(tmp_path):
    assert advisor.guide_objectives(tmp_path, "Nobody") is None


class FakeSession:
    is_available = True

    def __init__(self):
        self.zones = []

    def apply_zone(self, zone):
        self.zones.append(zone)

    def submit_candidate(self, raw, name, slot, source):
        return 1

    def measure(self, slot, raw, cid, source, main_skill):
        assert main_skill == "Entangle" and source == "ranking"
        gain = {"Weapon 1": (100.0, 180.0, 500.0, 500.0), "Belt": (100.0, 100.0, 500.0, 600.0)}[slot]
        return SimpleNamespace(dps_before=gain[0], dps_after=gain[1], ehp_before=gain[2], ehp_after=gain[3],
                               current_item_name="cur")


def test_rank_slots_orders_by_pob_gain(runtime):
    s = FakeSession()
    out = advisor.rank_slots(runtime, "P", s)
    assert [r["slot"] for r in out["rows"]] == ["Weapon 1", "Belt"]
    assert out["rows"][0]["dps_pct"] == 0.8 and out["rows"][1]["ehp_pct"] == 0.2
    assert s.zones == ["The Titan Grotto"]


def test_rank_slots_needs_pob(runtime):
    assert advisor.rank_slots(runtime, "P", None) == {"error": "PoB2 tidak tersedia."}
