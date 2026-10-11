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


def test_corrupt_guide_file_is_skipped(tmp_path):
    save_guide(tmp_path, _profile("ok"))
    (tmp_path / "guides" / "bad.json").write_text("{not json", encoding="utf-8")
    assert load_guide(tmp_path, "bad") is None
    assert [g.slug for g in list_guides(tmp_path)] == ["ok"]


def test_singular_item_class_fallback():
    from companion.builds.guide import singular_item_class
    assert singular_item_class("Daggers") == "Dagger"
    assert singular_item_class("Staves") == "Staff"
    assert singular_item_class("Wands") == "Wand"


def test_corrupt_assignments_file_returns_empty(tmp_path):
    save_guide(tmp_path, _profile())
    (tmp_path / "guides" / "_assignments.json").write_text("{oops", encoding="utf-8")
    assert get_assignment(tmp_path, "c1") == (None, None)


@pytest.mark.parametrize("content", ["[1, 2]", '{"c1": "g"}', '{"c1": null}'])
def test_wrong_shape_assignments_do_not_raise(tmp_path, content):
    save_guide(tmp_path, _profile())
    (tmp_path / "guides" / "_assignments.json").write_text(content, encoding="utf-8")
    assert get_assignment(tmp_path, "c1") == (None, None)
    set_assignment(tmp_path, "c2", "g", None)
    assert get_assignment(tmp_path, "c2") == ("g", None)


def test_bom_files_are_read(tmp_path):
    save_guide(tmp_path, _profile())
    gdir = tmp_path / "guides"
    (gdir / "g.json").write_text("﻿" + (gdir / "g.json").read_text(encoding="utf-8"), encoding="utf-8")
    (gdir / "_assignments.json").write_text('﻿{"c1": {"guide_slug": "g", "stage_override": null}}', encoding="utf-8")
    assert load_guide(tmp_path, "g") is not None
    set_assignment(tmp_path, "c2", "g", None)
    assert get_assignment(tmp_path, "c1") == ("g", None)  # BOM file not wiped by the write


def test_unreadable_assignments_kept_as_backup_before_overwrite(tmp_path):
    save_guide(tmp_path, _profile())
    path = tmp_path / "guides" / "_assignments.json"
    path.write_text("{oops", encoding="utf-8")
    set_assignment(tmp_path, "c1", "g", None)
    assert get_assignment(tmp_path, "c1") == ("g", None)
    assert (tmp_path / "guides" / "_assignments.json.corrupt").read_text(encoding="utf-8") == "{oops"
