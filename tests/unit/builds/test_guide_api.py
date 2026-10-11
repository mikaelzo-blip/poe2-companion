import http.client
import json
import threading
from pathlib import Path

import pytest

from companion.dashboard_api import (
    delete_guide_payload,
    get_available_guides,
    import_guide_payload,
    set_character_guide_payload,
    update_guide_rules_payload,
)
from companion.dashboard_server import DashboardRequestHandler, ThreadingDashboardServer

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "guides"
NAMES = [
    "fubgun-flameblast-oil-grenade",
    "naviras-fracturing-varashta-league-starter",
    "plant-oracle-druid-leveling-build-guide",
]


def _text(name):
    return (FIX / f"{name}.json").read_text(encoding="utf-8")


def _import_all(tmp_path):
    return [import_guide_payload({"text": _text(n)}, tmp_path) for n in NAMES]


def test_import_all_fixtures_and_list(tmp_path):
    for res in _import_all(tmp_path):
        assert res["success"] is True
    out = get_available_guides(tmp_path)
    assert len(out["guides"]) == 3
    assert out["active"] == {"guide": None, "stage_override": None}
    g = next(g for g in out["guides"] if g["slug"] == NAMES[0])
    assert g["has_pob"] is True
    assert (tmp_path / "guides" / f"{NAMES[0]}.xml").exists()
    assert {"id", "title", "min_level", "max_level", "auto"} <= set(g["stages"][0])


@pytest.mark.parametrize("text", ["halo", '{"format": "mobalytics-guide-v1", "vari', '{"format": "other"}'])
def test_bad_import_writes_nothing(tmp_path, text):
    res = import_guide_payload({"text": text}, tmp_path)
    assert "error" in res and "success" not in res
    assert not list((tmp_path / "guides").glob("*")) if (tmp_path / "guides").exists() else True


def test_pobb_import_uses_fetch(tmp_path, monkeypatch):
    import base64
    import zlib

    xml = "<PathOfBuilding2><Items activeItemSet='1'><ItemSet id='1' title='A'/></Items></PathOfBuilding2>"
    code = base64.urlsafe_b64encode(zlib.compress(xml.encode())).decode()
    monkeypatch.setattr("companion.builds.pob_code.fetch_pobb_code", lambda url, opener=None: code)
    res = import_guide_payload({"text": "https://pobb.in/abc123"}, tmp_path)
    assert res["success"] is True and res["stages"] == 1


def test_invalid_rule_rejected_rules_unchanged(tmp_path):
    import_guide_payload({"text": _text(NAMES[0])}, tmp_path)
    ok = update_guide_rules_payload(
        {"slug": NAMES[0], "rules": [{"pattern": "foo", "reason": "r"}]}, tmp_path)
    assert ok["success"] is True
    bad = update_guide_rules_payload(
        {"slug": NAMES[0], "rules": [{"pattern": "(", "reason": "r"}]}, tmp_path)
    assert bad["error"].startswith("Pola regex tidak valid")
    g = get_available_guides(tmp_path)["guides"][0]
    assert [r["pattern"] for r in g["breaker_rules"]] == ["foo"]


def test_unknown_slug_errors(tmp_path):
    assert "error" in update_guide_rules_payload({"slug": "nope", "rules": []}, tmp_path)
    assert "error" in delete_guide_payload({"slug": "nope"}, tmp_path)
    assert "error" in set_character_guide_payload(
        {"character_id": "C", "guide": "nope", "stage_override": None}, tmp_path)


def test_assignment_and_delete(tmp_path):
    import_guide_payload({"text": _text(NAMES[0])}, tmp_path)
    res = set_character_guide_payload(
        {"character_id": "C", "guide": NAMES[0], "stage_override": None}, tmp_path)
    assert res["success"] is True
    assert get_available_guides(tmp_path, "C")["active"] == {"guide": NAMES[0], "stage_override": None}
    assert delete_guide_payload({"slug": NAMES[0]}, tmp_path)["success"] is True
    assert get_available_guides(tmp_path, "C")["guides"] == []


def test_post_guides_foreign_origin_403():
    httpd = ThreadingDashboardServer(("127.0.0.1", 0), DashboardRequestHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
        conn.request("POST", "/api/guides", body="{}",
                     headers={"Origin": "http://evil.example", "Content-Length": "2"})
        assert conn.getresponse().status == 403
        conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()


def _moba(**over):
    d = {"format": "poe2-companion-guide/1", "slug": "s", "name": "N",
         "variants": [{"id": "1", "title": "t", "items": {}}]}
    d.update(over)
    return json.dumps(d)


def _empty(tmp_path):
    g = tmp_path / "guides"
    return not g.exists() or not list(g.glob("*"))


def test_malformed_structures_give_indonesian_error(tmp_path):
    from companion.builds.mobalytics import FORMAT
    import base64
    import zlib

    bad = [
        _moba(format=FORMAT, variants=[{}]),
        _moba(format=FORMAT, variants=[{"id": "1", "items": {"helmet": {"name": "x", "stats": [1]}}}]),
        _moba(format=FORMAT, variants="abc"),
    ]
    code = base64.urlsafe_b64encode(zlib.compress(b"<PathOfBuilding2><Items>")).decode()
    bad.append(code)
    for text in bad:
        res = import_guide_payload({"text": text}, tmp_path)
        assert "error" in res, text
        assert res["error"].startswith(("Struktur guide tidak valid", "XML PoB2 tidak valid", "Panduan")), res
    assert _empty(tmp_path)


def test_nameless_item_skipped_with_warning(tmp_path):
    from companion.builds.mobalytics import FORMAT

    items = {"helmet": {"item_class": "helmet"}, "gloves": {"name": "G", "item_class": "gloves"}}
    res = import_guide_payload({"text": _moba(format=FORMAT, variants=[{"id": "1", "items": items}])}, tmp_path)
    assert res["success"] and any("tanpa nama" in w for w in res["warnings"])
    from companion.builds.store import load_guide
    assert list(load_guide(tmp_path, "s").stages[0].items) == ["Gloves"]


def test_overwrite_warns_and_stage_override_validated(tmp_path):
    import_guide_payload({"text": _text(NAMES[0])}, tmp_path)
    res = import_guide_payload({"text": _text(NAMES[0])}, tmp_path)
    assert any("ditimpa" in w for w in res["warnings"])
    res = set_character_guide_payload(
        {"character_id": "C", "guide": NAMES[0], "stage_override": "zzz"}, tmp_path)
    assert "error" in res
    assert get_available_guides(tmp_path, "C")["active"]["guide"] is None


def test_internal_error_in_assign_level_ranges_propagates(monkeypatch, tmp_path):
    def boom(profile):
        raise KeyError("internal_bug")

    monkeypatch.setattr("companion.builds.mobalytics.assign_level_ranges", boom)
    with pytest.raises(KeyError):
        import_guide_payload({"text": _text(NAMES[0])}, tmp_path)


def test_stage_override_edge_cases(tmp_path):
    import_guide_payload({"text": _text(NAMES[0])}, tmp_path)
    for guide, ov in ((NAMES[0], ["1"]), (NAMES[0], {"a": 1}), (None, "1")):
        res = set_character_guide_payload(
            {"character_id": "C", "guide": guide, "stage_override": ov}, tmp_path)
        assert "error" in res
    stage = get_available_guides(tmp_path)["guides"][0]["stages"][0]["id"]
    assert set_character_guide_payload(
        {"character_id": "C", "guide": NAMES[0], "stage_override": stage}, tmp_path)["success"]
    assert get_available_guides(tmp_path, "C")["active"] == {"guide": NAMES[0], "stage_override": stage}


def test_pob_code_reimport_gets_unique_slug(tmp_path):
    import base64
    import zlib

    xml = "<PathOfBuilding2><Items activeItemSet='1'><ItemSet id='1' title='A'/></Items></PathOfBuilding2>"
    code = base64.urlsafe_b64encode(zlib.compress(xml.encode())).decode()
    slugs = [import_guide_payload({"text": code}, tmp_path)["slug"] for _ in range(3)]
    assert len({*slugs}) == 3 and slugs[1] == slugs[0] + "-2" and slugs[2] == slugs[0] + "-3"


def test_bad_pob_code_sets_has_pob_false_and_removes_stale_xml(tmp_path):
    from companion.builds.store import load_guide, load_guide_xml

    d = json.loads(_text(NAMES[0]))
    import_guide_payload({"text": json.dumps(d)}, tmp_path)
    slug = d["slug"]
    assert load_guide_xml(tmp_path, slug) is not None
    d["pob_code"] = "not-a-code"
    res = import_guide_payload({"text": json.dumps(d)}, tmp_path)
    assert res["success"] and any("PoB2 dilewati" in w for w in res["warnings"])
    assert load_guide(tmp_path, slug).has_pob is False
    assert load_guide_xml(tmp_path, slug) is None


def test_import_fubgun_fixture_gets_default_rule(tmp_path):
    from companion.builds.store import load_guide

    import_guide_payload({"text": _text(NAMES[0])}, tmp_path)
    assert load_guide(tmp_path, NAMES[0]).breaker_rules[0].from_level == 52


def test_mobalytics_import_pob_stage_matches_active_set(tmp_path):
    from companion.builds.store import load_guide

    slug = "naviras-fracturing-varashta-league-starter"
    res = import_guide_payload({"text": _text(slug)}, tmp_path)
    assert res["success"] is True
    guide = load_guide(tmp_path, slug)
    assert guide is not None
    late_stage = next(s for s in guide.stages if s.title == "Late Endgame")
    assert guide.pob_stage_id == late_stage.id
    assert guide.pob_stage_id != guide.stages[-1].id

