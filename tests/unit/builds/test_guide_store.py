import pytest
from pydantic import ValidationError

from companion.builds.guide import BreakerRule, GuideProfile, GuideStage
from companion.builds.store import (
    delete_guide, get_assignment, list_guides, load_guide, load_guide_xml,
    save_guide, set_assignment, set_breaker_rules, slugify,
)


def _profile(slug="g", name="G", rules=()):
    return GuideProfile(slug=slug, name=name, imported_at="2026-01-01T00:00:00Z",
                        stages=[GuideStage(id="s1", title="S1")], breaker_rules=list(rules))


def test_slugify():
    assert slugify("0.5.5 Fubgun Flameblast") == "0-5-5-fubgun-flameblast"
    assert slugify("../x") == "x"
    assert len(slugify("a" * 100)) == 60
    with pytest.raises(ValueError, match="Nama guide tidak valid"):
        slugify("🔥")


def test_round_trip_and_delete(tmp_path):
    save_guide(tmp_path, _profile("b", "B"), pob_xml="<x/>")
    save_guide(tmp_path, _profile("a", "A"))
    assert load_guide(tmp_path, "b").name == "B"
    assert load_guide_xml(tmp_path, "b") == "<x/>"
    assert load_guide(tmp_path, "nope") is None
    assert [g.slug for g in list_guides(tmp_path)] == ["a", "b"]
    assert delete_guide(tmp_path, "b") is True
    assert not (tmp_path / "guides" / "b.json").exists()
    assert not (tmp_path / "guides" / "b.xml").exists()
    assert delete_guide(tmp_path, "b") is False


def test_resave_keeps_stored_rules(tmp_path):
    save_guide(tmp_path, _profile())
    set_breaker_rules(tmp_path, "g", [BreakerRule(pattern="foo", reason="r")])
    out = save_guide(tmp_path, _profile(rules=[]))
    assert [r.pattern for r in out.breaker_rules] == ["foo"]
    assert [r.pattern for r in load_guide(tmp_path, "g").breaker_rules] == ["foo"]


def test_assignment(tmp_path):
    assert get_assignment(tmp_path, "c1") == (None, None)
    save_guide(tmp_path, _profile())
    set_assignment(tmp_path, "c1", "g", "s1")
    assert get_assignment(tmp_path, "c1") == ("g", "s1")
    delete_guide(tmp_path, "g")
    assert get_assignment(tmp_path, "c1") == (None, None)


def test_bad_regex():
    with pytest.raises(ValidationError):
        BreakerRule(pattern="(", reason="r")


def test_hostile_slug_stays_inside(tmp_path):
    save_guide(tmp_path, _profile(slug="../evil"))
    assert (tmp_path / "guides" / "evil.json").exists()
    assert not (tmp_path / "evil.json").exists()
