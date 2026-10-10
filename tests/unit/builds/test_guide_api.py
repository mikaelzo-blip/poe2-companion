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
        _moba(format=FORMAT, variants=[{"id": "1", "items": {"helmet": {"item_class": "x"}}}]),
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


def test_overwrite_warns_and_stage_override_validated(tmp_path):
    import_guide_payload({"text": _text(NAMES[0])}, tmp_path)
    res = import_guide_payload({"text": _text(NAMES[0])}, tmp_path)
    assert any("ditimpa" in w for w in res["warnings"])
    res = set_character_guide_payload(
        {"character_id": "C", "guide": NAMES[0], "stage_override": "zzz"}, tmp_path)
    assert "error" in res
    assert get_available_guides(tmp_path, "C")["active"]["guide"] is None
