"""Build Tracker payload: per-act gem/quest checklist, computed gear rows, ticks persisted per character."""
from __future__ import annotations

import json

import pytest

from companion import dashboard_api
from companion.builds import advisor
from companion.builds.guide import GemNote, GuideProfile, GuideStage, PassiveNotable, QuestReward, StageItem
from companion.builds.store import save_guide, set_assignment

BELT = StageItem(slot="Belt", name="Plate Belt", item_class="Belt", mods=["+100 to maximum Life", "+31% to Fire Resistance"])
BODY = StageItem(slot="Body Armour", name="Heartcarver Mantle", item_class="Body Armour", is_unique=True)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    save_guide(tmp_path, GuideProfile(
        slug="plant", name="Plant", imported_at="2026-01-01T00:00:00Z",
        stages=[GuideStage(id="s", title="Leveling", items={"Belt": BELT, "Body Armour": BODY},
                           notables=[PassiveNotable(name="Radial Force"),
                                     PassiveNotable(name="Forced Outcome", kind="ASCENDANCY_LARGE")])],
        gem_notes=[GemNote(title="", steps=["Intro"]), GemNote(title="Act 2", steps=["Zenith I"]),
                   GemNote(title="Act 4 & Interludes", steps=["Cast on Critical"])],
        quest_rewards=[QuestReward(act="Interlude", area="Qimah", quest="Tabana's Pillar", reward="+5% all res"),
                       QuestReward(act="Act 2", area="Valley of the Titans", quest="Medallion", reward="+1 Charm Slot")],
        tree_hints=["Respec at The Hooded One"],
    ))
    set_assignment(tmp_path, "P", "plant", None)
    (tmp_path / "characters").mkdir()
    (tmp_path / "characters" / "P.json").write_text(
        json.dumps({"level": {"value": 23}, "current_zone": {"value": "The Titan Grotto"}}), encoding="utf-8")
    gear = {"Belt": "Item Class: Belts\nRarity: Rare\nY\nRawhide Belt\n--------\nItem Level: 20\n--------\n"
                    "+60 to maximum Life",
            "Body Armour": "Item Class: Body Armours\nRarity: Unique\nHeartcarver Mantle\nWayfarer Jacket"}
    monkeypatch.setattr(advisor, "get_current_raw", lambda rt, cid, slot, pob=None: gear.get(slot, ""))
    return tmp_path


def test_sections_grouped_by_act_in_campaign_order(runtime):
    t = dashboard_api.get_build_tracker(runtime, "P")
    assert t["act"] == "Act 2"
    assert [s["key"] for s in t["sections"]] == ["Umum", "Act 2", "Act 4", "Interlude"]
    act2 = next(s for s in t["sections"] if s["key"] == "Act 2")
    assert act2["current"] and [(i["kind"], i["text"]) for i in act2["items"]] == [("gem", "Zenith I"), ("quest", "Medallion")]
    assert act2["items"][1]["detail"] == "+1 Charm Slot"
    assert [p["text"] for p in t["passives"]] == ["Radial Force", "Forced Outcome", "Respec at The Hooded One"]


def test_gear_rows_score_missing_mods_and_match_uniques_by_name(runtime):
    gear = {r["slot"]: r for r in dashboard_api.get_build_tracker(runtime, "P")["gear"]}
    assert gear["Belt"]["match_pct"] == 50 and gear["Belt"]["missing"] == ["+31% to Fire Resistance"]
    assert gear["Body Armour"]["done"] and not gear["Belt"]["done"]


def test_ticks_persist_and_count_toward_progress(runtime):
    t = dashboard_api.get_build_tracker(runtime, "P")
    medallion = next(i for s in t["sections"] for i in s["items"] if i["text"] == "Medallion")
    total = t["progress"]["total"]
    assert total == 3 + 2 + 2 + 2  # gem steps, quests, notables (hints not ticked), gear rows
    assert t["progress"]["done"] == 1  # the equipped unique
    assert dashboard_api.set_tracker_tick_payload({"id": medallion["id"], "done": True}, runtime, "P")["success"]
    again = dashboard_api.get_build_tracker(runtime, "P")
    assert next(i for s in again["sections"] for i in s["items"] if i["id"] == medallion["id"])["done"]
    assert again["progress"]["done"] == 2
    assert json.loads((runtime / "tracker" / "P.json").read_text(encoding="utf-8")) == {"done": [medallion["id"]]}
    dashboard_api.set_tracker_tick_payload({"id": medallion["id"], "done": False}, runtime, "P")
    assert dashboard_api.get_build_tracker(runtime, "P")["progress"]["done"] == 1


def test_tick_rejects_bad_ids_and_character_paths(runtime):
    assert "error" in dashboard_api.set_tracker_tick_payload({"id": "../x", "done": True}, runtime, "P")
    assert "error" in dashboard_api.set_tracker_tick_payload({"id": "gem:0123456789ab", "done": True}, runtime, "../P")
    assert not (runtime / "tracker").exists()


def test_no_guide_is_an_error(runtime):
    assert "error" in dashboard_api.get_build_tracker(runtime, "Q")
