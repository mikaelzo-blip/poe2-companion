import json
from pathlib import Path

import pytest

from companion.builds.mobalytics import parse_mobalytics_guide
from companion.builds.guide import GuideProfile, GuideStage
from companion.builds.stages import assign_level_ranges, parse_level_range, resolve_stage

GUIDES = Path(__file__).resolve().parents[2] / "fixtures" / "guides"


def _profile(prefix):
    p = next(GUIDES.glob(f"{prefix}*.json"))
    return parse_mobalytics_guide(json.loads(p.read_text(encoding="utf-8")))[0]


@pytest.mark.parametrize("title,expected", [
    ("lvl 1-14", (1, 14, False)),
    ("Level 20-30", (20, 30, False)),
    ("Lv 5-9", (5, 9, False)),
    ("lvl 52 Swap", (52, 52, False)),
    ("lvl 85", (85, 85, False)),
    ("33-51", (33, 51, False)),
    ("lvl 1–14", (1, 14, False)),
    ("33—51", (33, 51, False)),
    ("Act 1", (1, 15, False)),
    ("Act 2", (16, 29, False)),
    ("Act 3", (30, 44, False)),
    ("Act 4", (45, 55, False)),
    ("Interlude", (56, 64, False)),
    ("Act 1 & 2 (Pre-Ascend)", (1, 29, False)),
    ("Act 4 to Endgame", (45, 64, False)),
    ("Early Endgame", (65, None, True)),
    ("Mageblood", (65, None, True)),
    ("DoT Cap", (65, None, True)),
    ("Uber Endgame", (65, None, True)),
    ("Random title", (None, None, False)),
])
def test_parse_level_range(title, expected):
    assert parse_level_range(title) == expected


def _ranges(p):
    return [(s.min_level, s.max_level) for s in p.stages], [s.auto for s in p.stages]


def test_fubgun_ranges():
    r, a = _ranges(_profile("fubgun"))
    assert r == [(1, 14), (15, 32), (33, 51), (52, 52), (53, 84), (85, 85),
                 (86, 100), (86, 100), (86, 100)]
    assert a == [True] * 7 + [False] * 2


def test_navira_ranges():
    r, a = _ranges(_profile("navira"))
    assert r == [(1, 15), (16, 29), (30, 44), (45, 64), (65, 100)] + [(65, 100)] * 3
    assert a == [True] * 5 + [False] * 3


def test_plant_oracle_single_stage():
    assert _ranges(_profile("plant"))[0] == [(1, 100)]


@pytest.mark.parametrize("prefix", ["fubgun", "navira", "plant"])
def test_every_level_resolves_to_one_auto_stage(prefix):
    p = _profile(prefix)
    for lvl in range(1, 101):
        hits = [s for s in p.stages if s.auto and s.min_level <= lvl <= s.max_level]
        assert len(hits) == 1, (prefix, lvl)


def test_resolve_stage():
    p = _profile("fubgun")
    assert resolve_stage(p, 60).title == "lvl 53-68"
    dot = next(s for s in p.stages if s.title == "DoT Cap")
    assert resolve_stage(p, 60, override_id=dot.id).title == "DoT Cap"
    assert resolve_stage(p, 60, override_id="nope").title == "lvl 53-68"
    assert resolve_stage(p, None) is p.stages[0]


@pytest.mark.parametrize("titles", [
    ["lvl 30-40", "lvl 1-10"],
    ["lvl 1-10", "lvl 1-10"],
    ["Endgame", "lvl 1-20"],
    ["A", "B", "C"],
    ["lvl 1-10", "Endgame", "lvl 20-30"],
    ["lvl 50-60"],
    ["Endgame"],
    ["lvl 120-130"],
    ["Endgame", "Mageblood"],
    ["lvl 1-64", "lvl 65-100", "Endgame", "Mageblood"],
    ["lvl 1-100", "Endgame", "Mageblood"],
])
def test_synthetic_titles_cover_all_levels_once(titles):
    p = GuideProfile(slug="x", name="x", imported_at="t",
                     stages=[GuideStage(id=str(i), title=t) for i, t in enumerate(titles)])
    out = assign_level_ranges(p)
    assert all(1 <= s.min_level <= s.max_level <= 100 for s in out.stages)
    for lvl in range(1, 101):
        assert sum(s.auto and s.min_level <= lvl <= s.max_level for s in out.stages) == 1, lvl


def _rng(titles):
    p = GuideProfile(slug="x", name="x", imported_at="t",
                     stages=[GuideStage(id=str(i), title=t) for i, t in enumerate(titles)])
    return [(s.min_level, s.max_level) for s in assign_level_ranges(p).stages]


def test_gap_extends_previous_stage():
    assert _rng(["lvl 1-40", "Endgame"]) == [(1, 64), (65, 100)]
    assert _rng(["lvl 50-60"]) == [(1, 100)]


def test_resolve_stage_fallback():
    p = GuideProfile(slug="x", name="x", imported_at="t", stages=[
        GuideStage(id="a", title="a", min_level=1, max_level=10),
        GuideStage(id="b", title="b", min_level=20, max_level=30)])
    assert resolve_stage(p, 15).id == "a"
    assert resolve_stage(p, 0).id == "a"
    assert resolve_stage(p, 200).id == "b"


def _stages(titles):
    p = GuideProfile(slug="g", name="G", imported_at="x",
                     stages=[GuideStage(id=str(i), title=t) for i, t in enumerate(titles)])
    return assign_level_ranges(p).stages


@pytest.mark.parametrize("titles,ranges", [
    (["Leveling", "Endgame"], [(1, 64, True), (65, 100, True)]),
    (["Campaign", "Maps"], [(1, 64, True), (65, 100, True)]),
    (["Act 1", "Campaign", "Endgame"], [(1, 15, True), (16, 64, True), (65, 100, True)]),
])
def test_unparsed_before_keyword_stage_ends_at_64(titles, ranges):
    st = _stages(titles)
    assert [(s.min_level, s.max_level, s.auto) for s in st] == ranges


def test_leveling_endgame_level_70_resolves_to_endgame():
    p = GuideProfile(slug="g", name="G", imported_at="x", stages=_stages(["Leveling", "Endgame"]))
    assert resolve_stage(p, 70).title == "Endgame"
    assert resolve_stage(p, 30).title == "Leveling"


def test_bare_early_mid_late_are_not_keywords():
    st = _stages(["Early Game", "Mid Game", "Late Game"])
    assert len(st) == 3 and all(s.auto for s in st)
    for lv in range(1, 101):
        assert sum(s.min_level <= lv <= s.max_level for s in st if s.auto) == 1


@pytest.mark.parametrize("title,expected", [
    ("Act 1-2", (1, 29, False)),
    ("Act 3-4 Leveling", (30, 55, False)),
    ("Lv 12", (12, 12, False)),
])
def test_act_pair_dash_and_lv(title, expected):
    assert parse_level_range(title) == expected
