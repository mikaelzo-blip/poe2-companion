"""Unit tests for Dashboard API evaluation and server endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from companion.dashboard_api import evaluate_item_payload
from companion.dashboard_server import CustomHandler, PROJECT_ROOT


SAMPLE_BOOTS_TEXT = """Item Class: Boots
Rarity: Rare
Brimstone Greaves
Iron Greaves
--------
Armour: 52
--------
Requirements:
Level: 14
Str: 12
--------
+16% to Fire Resistance
+14% to Cold Resistance
15% increased Movement Speed
+18 to maximum Life"""

SAMPLE_WEAPON_TEXT = """Item Class: Crossbows
Rarity: Rare
Dire Core
Tense Crossbow
--------
Physical Damage: 25-68
Critical Hit Chance: 5.00%
Attacks per Second: 1.25
--------
Requirements:
Level: 14
Dex: 20
--------
Adds 5 to 12 Physical Damage
+14 to Dexterity"""

SAMPLE_RING_TEXT = """Item Class: Rings
Rarity: Rare
Gold Ring
Iron Ring
--------
Requirements:
Level: 10
--------
+20% to Fire Resistance
+15 to maximum Life"""

SAMPLE_BODY_ARMOUR_TEXT = """Item Class: Body Armours
Rarity: Rare
Dragon Carapace
Chestplate
--------
Armour: 198
--------
Requirements:
Level: 16
Str: 28
--------
+48 to maximum Life
+22% to Fire Resistance
+16% to Cold Resistance
+14 to Strength"""

SAMPLE_AMULET_TEXT = """Item Class: Amulets
Rarity: Rare
Beast Medallion
Amber Amulet
--------
Requirements:
Level: 14
--------
+18 to Strength
+28 to maximum Life
+15% to All Elemental Resistances"""






















def test_import_character_payload(tmp_path: Path) -> None:
    from companion.dashboard_api import import_character_payload

    sample_ggg_payload = {
        "character": {"name": "BOMSHAK", "level": 17, "class": "Mercenary"},
        "items": [
            {
                "name": "Maelström Keep",
                "typeLine": "Shrouded Vest",
                "inventoryId": "BodyArmour",
                "frameType": 2,
                "properties": [{"name": "Evasion Rating", "values": [["209", 1]]}],
                "explicitMods": [
                    "+11 to Evasion Rating",
                    "50% increased Evasion Rating",
                    "+26 to Maximum Life",
                    "+10% to Lightning Resistance",
                    "5.8 Life Regeneration per second",
                ],
            },
            {
                "name": "Amber Amulet",
                "typeLine": "Amber Amulet",
                "inventoryId": "Amulet",
                "frameType": 1,
                "implicitMods": ["+15 to Strength"],
                "explicitMods": ["+10 to maximum Life"],
            },
        ],
    }

    result = import_character_payload(
        {"character_id": "test_import_char", "character_data": sample_ggg_payload},
        runtime_dir=tmp_path,
    )
    assert result.get("success") is True
    assert result.get("imported_slots") == 2
    assert "body_armour" in result.get("slots", [])
    assert "amulet" in result.get("slots", [])


def test_import_character_payload_overwrites_conflicting_manual_slot(tmp_path: Path) -> None:
    from companion.dashboard_api import import_character_payload
    from companion.equipment.loadout_cli import load_loadout, save_loadout
    from companion.equipment.loadout import EquippedLoadout
    from companion.equipment.schema import ItemCandidate, SlotConflictTopology, SlotOccupancy, SlotType
    from companion.equipment.baseline import BaselineSource
    from companion.state.provenance import VerificationState

    # Pre-populate loadout with manual Ruby Ring
    loadout = EquippedLoadout.create_draft(character_id="test_overwrite_char")
    item = ItemCandidate(
        item_id="manual_ring",
        name="Ruby Ring",
        base_type="Ruby Ring",
        slot=SlotType.RING_2,
        slot_occupancy=SlotOccupancy.SINGLE_SLOT,
        slot_conflict_topology=SlotConflictTopology(occupied_slots=[SlotType.RING_2]),
    )
    loadout.set_slot(SlotType.RING_2, item, source=BaselineSource.CLIPBOARD_ITEM_TEXT)
    loadout.finalize()
    save_loadout(tmp_path, loadout)

    sample_api_payload = {
        "character": {"name": "test_overwrite_char", "level": 20, "class": "Mercenary"},
        "items": [
            {
                "name": "",
                "typeLine": "Smouldering Iron Ring of the Starfish",
                "inventoryId": "Ring2",
                "frameType": 1,
                "explicitMods": ["Adds 5 to 9 Fire damage to Attacks"],
            },
        ],
    }

    # 1. With overwrite=True (default)
    res = import_character_payload(
        {"character_id": "test_overwrite_char", "character_data": sample_api_payload, "overwrite": True},
        runtime_dir=tmp_path,
    )
    assert res.get("success") is True
    updated_loadout = load_loadout(tmp_path, "test_overwrite_char")
    r2_entry = updated_loadout.get_slot(SlotType.RING_2)
    assert r2_entry is not None
    assert r2_entry.item.name == "Smouldering Iron Ring of the Starfish"
    assert r2_entry.verification == VerificationState.VERIFIED

    # 2. Reset back to manual and test with overwrite=False
    loadout2 = EquippedLoadout.create_draft(character_id="test_overwrite_char")
    loadout2.set_slot(SlotType.RING_2, item, source=BaselineSource.CLIPBOARD_ITEM_TEXT)
    loadout2.finalize()
    save_loadout(tmp_path, loadout2)

    res_no_ow = import_character_payload(
        {"character_id": "test_overwrite_char", "character_data": sample_api_payload, "overwrite": False},
        runtime_dir=tmp_path,
    )
    assert res_no_ow.get("success") is True
    no_ow_loadout = load_loadout(tmp_path, "test_overwrite_char")
    r2_entry_no_ow = no_ow_loadout.get_slot(SlotType.RING_2)
    assert r2_entry_no_ow is not None
    assert r2_entry_no_ow.item.name == "Ruby Ring"
    assert r2_entry_no_ow.verification == VerificationState.CONFLICTING


def test_dashboard_server_http_evaluate_endpoint() -> None:
    import socketserver
    import threading
    import urllib.request
    from unittest.mock import patch

    with patch("companion.dashboard_server.get_or_create_pob_session", return_value=None):
        with socketserver.TCPServer(("127.0.0.1", 0), CustomHandler) as httpd:
            port = httpd.server_address[1]
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()

            # 1. Test POST /api/evaluate-item
            post_data = json.dumps({
                "raw_text": SAMPLE_BOOTS_TEXT,
                "character_id": "BOMSHAK",
                "stage": "lvl 1-14",
            }).encode("utf-8")

            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/evaluate-item",
                data=post_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                assert resp.status == 200
                body = json.loads(resp.read().decode("utf-8"))
                assert body.get("success") is True
                assert body.get("item_name") == "Brimstone Greaves"

            # 2. Test GET /api/clipboard-poll
            req_poll = urllib.request.Request(f"http://127.0.0.1:{port}/api/clipboard-poll")
            with urllib.request.urlopen(req_poll, timeout=5) as resp:
                assert resp.status == 200
                body = json.loads(resp.read().decode("utf-8"))
                assert "has_new_item" in body

            # Test GET /api/get-clipboard
            req_get_clip = urllib.request.Request(f"http://127.0.0.1:{port}/api/get-clipboard")
            with urllib.request.urlopen(req_get_clip, timeout=5) as resp:
                assert resp.status == 200
                body = json.loads(resp.read().decode("utf-8"))
                assert "clipboard_text" in body

            # 3. Test POST /api/equip-item
            test_char_id = "test_dashboard_char"
            equip_data = json.dumps({
                "raw_text": SAMPLE_BOOTS_TEXT,
                "character_id": test_char_id,
                "slot": "boots",
            }).encode("utf-8")
            req_equip = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/equip-item",
                data=equip_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req_equip, timeout=5) as resp:
                assert resp.status == 200
                body = json.loads(resp.read().decode("utf-8"))
                assert body.get("success") is True

            # 4. Test GET /api/status
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status?char_id=BOMSHAK", timeout=5) as resp:
                assert resp.status == 200
                status_body = json.loads(resp.read().decode("utf-8"))
                assert "status" in status_body
                assert "loadout" in status_body
                assert status_body.get("active_character_id") == "BOMSHAK"

            # 4.1 Test GET /api/status?char_id=DaisyofWar
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status?char_id=DaisyofWar", timeout=5) as resp:
                assert resp.status == 200
                status_body_daisy = json.loads(resp.read().decode("utf-8"))
                assert status_body_daisy.get("active_character_id") == "DaisyofWar"

            # 4.2 Test GET /api/status without query params
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=5) as resp:
                assert resp.status == 200
                status_body_bare = json.loads(resp.read().decode("utf-8"))
                assert "active_character_id" in status_body_bare

            # 4b. Test GET /api/account-characters
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/account-characters?account=mikaelzo%235674", timeout=5) as resp:
                assert resp.status == 200
                acc_body = json.loads(resp.read().decode("utf-8"))
                assert acc_body.get("account") == "mikaelzo#5674"
                assert "characters" in acc_body

            # 4b2. Test GET /api/guides
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/guides", timeout=5) as resp:
                assert resp.status == 200
                guides_body = json.loads(resp.read().decode("utf-8"))
                assert "guides" in guides_body

            # 4c. Test POST /api/select-character
            select_data = json.dumps({"character_id": "BOMSHAK"}).encode("utf-8")
            req_sel = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/select-character",
                data=select_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req_sel, timeout=5) as resp:
                assert resp.status == 200
                sel_body = json.loads(resp.read().decode("utf-8"))
                assert sel_body.get("success") is True
                assert sel_body.get("active_character_id") == "BOMSHAK"

            # 4d. Test POST /api/update-stats
            stats_data = json.dumps({
                "character_id": "BOMSHAK",
                "level": 37,
                "strength": 48,
                "dexterity": 85,
                "intelligence": 53,
                "life": 723,
                "mana": 284,
                "spirit": 30,
                "energy_shield": 47,
                "armour": 112,
                "evasion": 465,
                "fire_res": 23,
                "cold_res": -3,
                "lightning_res": -4,
                "chaos_res": 0,
            }).encode("utf-8")
            req_stats = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/update-stats",
                data=stats_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req_stats, timeout=5) as resp:
                assert resp.status == 200
                stats_res = json.loads(resp.read().decode("utf-8"))
                assert stats_res.get("success") is True
                assert stats_res.get("character_id") == "BOMSHAK"


            # 5. Test GET static assets (HTML, CSS, JS)
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
                assert resp.status == 200
                html_text = resp.read().decode("utf-8")
                assert "compare-history-container" in html_text
                assert "TARGET LOADOUT SLOT" in html_text

            with urllib.request.urlopen(f"http://127.0.0.1:{port}/js/compare.js", timeout=5) as resp:
                assert resp.status == 200
                assert resp.headers["Content-Type"].startswith("text/javascript")
                js_text = resp.read().decode("utf-8")
                assert "SLOT_LABELS" in js_text
                assert "export function recordSlotComparison" in js_text

            with urllib.request.urlopen(f"http://127.0.0.1:{port}/style.css", timeout=5) as resp:
                assert resp.status == 200
                css_text = resp.read().decode("utf-8")
                assert "--accent-gold" in css_text

            httpd.shutdown()

        # Clean up test character loadout
        test_loadout_file = PROJECT_ROOT / "runtime" / "loadouts" / f"{test_char_id}.json"
        if test_loadout_file.exists():
            test_loadout_file.unlink()


def test_update_loadout_item_payload_set2_weapons(tmp_path: Path) -> None:
    from companion.dashboard_api import update_loadout_item_payload
    from companion.equipment.loadout_cli import load_loadout
    from companion.equipment.schema import SlotType, WeaponSetContext

    # Equip to set2_main_hand
    res1 = update_loadout_item_payload(
        {
            "raw_text": SAMPLE_WEAPON_TEXT,
            "character_id": "test_set2_hero",
            "slot": "set2_main_hand",
        },
        runtime_dir=tmp_path,
    )
    assert res1.get("success") is True, res1.get("error")
    assert res1.get("slot") == "main_hand"

    # Verify loadout has set2 weapon
    loadout = load_loadout(tmp_path, "test_set2_hero")
    assert loadout is not None
    entry = loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_2)
    assert entry is not None
    assert entry.item.name == "Dire Core"


def test_import_character_payload_persists_baseline_and_state(tmp_path: Path) -> None:
    from companion.dashboard_api import import_character_payload
    from companion.equipment.baseline_cli import load_baseline
    from companion.state.store import CharacterStateStore

    sample_payload = {
        "character": {"name": "TestSaver", "level": 25, "class": "Mercenary"},
        "items": [
            {
                "name": "Brimstone Greaves",
                "typeLine": "Iron Greaves",
                "inventoryId": "Boots",
                "frameType": 2,
                "explicitMods": ["+30 to maximum Life", "+15% to Fire Resistance"],
            }
        ],
    }

    res = import_character_payload(
        {"character_id": "TestSaver", "character_data": sample_payload},
        runtime_dir=tmp_path,
    )
    assert res.get("success") is True

    # 1. Baseline must be persisted on disk
    baseline = load_baseline(tmp_path, "TestSaver")
    assert baseline is not None
    assert baseline.character_id == "TestSaver"

    # 2. Character state must be persisted with correct level & class
    store = CharacterStateStore(runtime_dir=tmp_path)
    state = store.load_character("TestSaver")
    assert state is not None
    assert state.character_name == "TestSaver"
    assert state.level.value == 25
    assert state.character_class == "Mercenary"










def test_account_characters_merge_api_and_local(tmp_path, monkeypatch):
    from companion import dashboard_api
    from companion.dashboard_api import get_account_characters
    monkeypatch.setattr(dashboard_api, "_list_api_characters", lambda now=None: [{"name": "BOMSHAK", "level": 60, "class": "Mercenary", "league": "Rise"}])
    (tmp_path / "characters").mkdir(); (tmp_path / "characters" / "Alt.json").write_text(json.dumps({"character_name": "Alt", "level": 5}))
    res = get_account_characters(runtime_dir=tmp_path)
    assert {c["name"]: c["league"] for c in res["characters"]} == {"BOMSHAK": "Rise", "Alt": "Local"}
    assert res["source"] == "api"


def test_account_characters_no_fake_fallback(tmp_path, monkeypatch):
    from companion import dashboard_api
    from companion.dashboard_api import get_account_characters
    monkeypatch.setattr(dashboard_api, "_list_api_characters", lambda now=None: [])
    res = get_account_characters(runtime_dir=tmp_path)
    assert res["characters"] == []
    assert res["source"] == "local"


def test_list_api_characters_is_cached(monkeypatch):
    from types import SimpleNamespace
    from companion import dashboard_api
    monkeypatch.setattr(dashboard_api, "_API_CHARS_CACHE", {})
    calls = []
    fake_api = SimpleNamespace(list_characters=lambda: calls.append(1) or [{"name": "A", "level": 1, "class": "W", "league": "S"}])
    fake_oauth = SimpleNamespace(get_valid_token=lambda: "t")
    monkeypatch.setattr(dashboard_api, "load_pob_mcp_modules", lambda: (fake_api, fake_oauth))
    dashboard_api._list_api_characters(now=0); dashboard_api._list_api_characters(now=100)
    assert len(calls) == 1


def test_account_characters_skips_non_dict_character_file(tmp_path, monkeypatch):
    from companion import dashboard_api
    from companion.dashboard_api import get_account_characters
    monkeypatch.setattr(dashboard_api, "_list_api_characters", lambda now=None: [])
    (tmp_path / "characters").mkdir()
    (tmp_path / "characters" / "Bad.json").write_text("[1, 2]")
    (tmp_path / "characters" / "Good.json").write_text(json.dumps({"character_name": "Good", "level": 3}))
    res = get_account_characters(runtime_dir=tmp_path)
    assert [c["name"] for c in res["characters"]] == ["Good"]


def test_load_pob_mcp_modules_zero_arg_resolves_backend(tmp_path, monkeypatch):
    import sys
    from companion.equipment import pob2_equipment_advisor as adv
    pkg = tmp_path / "server" / "pob_mcp"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "poe_api.py").write_text("MARK = 'api'")
    (pkg / "poe_oauth.py").write_text("MARK = 'oauth'")
    monkeypatch.setattr(adv, "resolve_pob2_backend_path", lambda: tmp_path)
    saved_path = list(sys.path)
    saved_mods = {k: v for k, v in sys.modules.items() if k == "pob_mcp" or k.startswith("pob_mcp.")}
    for k in saved_mods:
        del sys.modules[k]
    try:
        mods = adv.load_pob_mcp_modules()
        assert mods is not None and mods[0].MARK == "api" and mods[1].MARK == "oauth"
    finally:
        sys.path[:] = saved_path
        for k in [k for k in sys.modules if k == "pob_mcp" or k.startswith("pob_mcp.")]:
            del sys.modules[k]
        sys.modules.update(saved_mods)


def _raise_not_logged_in():
    raise RuntimeError("not logged in")


@pytest.mark.parametrize("modules, expected", [
    (None, "POB2_MCP_NOT_FOUND"),
    ((SimpleNamespace(), SimpleNamespace(get_valid_token=lambda: "")), "OAUTH_REQUIRED"),
    ((SimpleNamespace(), SimpleNamespace(get_valid_token=_raise_not_logged_in)), "OAUTH_REQUIRED"),
    ((SimpleNamespace(fetch_character_raw=MagicMock(side_effect=RuntimeError("rate limited (429)"))),
      SimpleNamespace(get_valid_token=lambda: "t")), "GGG_API_ERROR"),
])
def test_fetch_public_profile_errors(tmp_path, monkeypatch, modules, expected):
    from companion import dashboard_api
    from companion.dashboard_api import fetch_public_profile
    monkeypatch.setattr(dashboard_api, "load_pob_mcp_modules", lambda: modules)
    res = fetch_public_profile("acc", "BOMSHAK", tmp_path)
    assert res["error"] == expected


def test_select_character_payload(tmp_path: Path) -> None:
    from companion.dashboard_api import select_character_payload

    # Create existing character file
    char_dir = tmp_path / "characters"
    char_dir.mkdir(parents=True, exist_ok=True)
    (char_dir / "DaisyofWar.json").write_text(
        json.dumps({
            "character_id": "DaisyofWar",
            "character_name": "DaisyofWar",
            "character_class": "Witch",
            "level": {"value": 71},
        }),
        encoding="utf-8",
    )

    res = select_character_payload({"character_id": "DaisyofWar"}, runtime_dir=tmp_path)
    assert res.get("success") is True
    assert res.get("active_character_id") == "DaisyofWar"

    # Verify active_character.json was written
    active_file = tmp_path / "active_character.json"
    assert active_file.exists()
    active_data = json.loads(active_file.read_text(encoding="utf-8"))
    assert active_data.get("active_character_id") == "DaisyofWar"




def test_get_dashboard_status_respects_explicit_char_id(tmp_path: Path) -> None:
    from companion.dashboard_api import get_dashboard_status

    # Set runtime_status.json with BOMSHAK
    status_file = tmp_path / "runtime_status.json"
    status_file.write_text(json.dumps({"active_character_id": "BOMSHAK"}), encoding="utf-8")

    # Create DaisyofWar character file
    char_dir = tmp_path / "characters"
    char_dir.mkdir(parents=True, exist_ok=True)
    daisy_file = char_dir / "DaisyofWar.json"
    daisy_file.write_text(json.dumps({"character_name": "DaisyofWar", "character_class": "Witch"}), encoding="utf-8")

    # Explicitly asking for DaisyofWar MUST return DaisyofWar
    res = get_dashboard_status(tmp_path, char_id="DaisyofWar")
    assert res["active_character_id"] == "DaisyofWar"
    assert res["character"].get("character_name") == "DaisyofWar"
    assert res["character"].get("character_class") == "Witch"


def test_get_dashboard_status_reads_active_character_json_when_none(tmp_path: Path) -> None:
    from companion.dashboard_api import get_dashboard_status

    active_file = tmp_path / "active_character.json"
    active_file.write_text(json.dumps({"active_character_id": "Mikaelzo"}), encoding="utf-8")

    char_dir = tmp_path / "characters"
    char_dir.mkdir(parents=True, exist_ok=True)
    mika_file = char_dir / "Mikaelzo.json"
    mika_file.write_text(json.dumps({"character_name": "Mikaelzo", "character_class": "Sorceress"}), encoding="utf-8")

    res = get_dashboard_status(tmp_path, char_id=None)
    assert res["active_character_id"] == "Mikaelzo"
    assert res["character"].get("character_class") == "Sorceress"












def test_update_character_stats_payload_updates_state_and_baseline(tmp_path: Path) -> None:
    """Verify that update_character_stats_payload updates CharacterState and Baseline with given stats."""
    from companion.dashboard_api import update_character_stats_payload, get_dashboard_status
    payload = {
        "character_id": "BOMSHAK",
        "level": 37,
        "ascendancy": "Gemling Legionnaire",
        "character_class": "Mercenary",
        "strength": 48,
        "dexterity": 85,
        "intelligence": 53,
        "life": 723,
        "mana": 284,
        "spirit": 30,
        "energy_shield": 47,
        "armour": 112,
        "evasion": 465,
        "fire_res": 23,
        "cold_res": -3,
        "lightning_res": -4,
        "chaos_res": 0,
    }
    result = update_character_stats_payload(payload, runtime_dir=tmp_path)
    assert result.get("success") is True
    assert result.get("character_id") == "BOMSHAK"

    status = get_dashboard_status(runtime_dir=tmp_path, char_id="BOMSHAK")
    char = status.get("character", {})
    assert char.get("level", {}).get("value") == 37
    assert char.get("attributes", {}).get("strength", {}).get("value") == 48
    assert char.get("attributes", {}).get("dexterity", {}).get("value") == 85
    assert char.get("attributes", {}).get("intelligence", {}).get("value") == 53
    # Check stage automatically advanced to lvl 33-51 for level 37
    assert char.get("build_progression", {}).get("active_stage") == "lvl 33-51"

    base = status.get("baseline", {})
    assert base.get("life", {}).get("value") == 723
    assert base.get("armour", {}).get("value") == 112
    assert base.get("evasion", {}).get("value") == 465
    assert base.get("energy_shield", {}).get("value") == 47
    assert base.get("effective_cold_res", {}).get("value") == -3





















def _inv_item(inv_id: str, type_line: str) -> dict:
    return {
        "name": "",
        "typeLine": type_line,
        "inventoryId": inv_id,
        "frameType": 1,
        "explicitMods": ["+10 to maximum Life"],
    }


def boots_item() -> dict:
    return _inv_item("Boots", "Rawhide Boots")


def gloves_item() -> dict:
    return _inv_item("Gloves", "Rawhide Gloves")


def test_official_import_clears_slots_missing_from_payload(tmp_path: Path) -> None:
    from companion.dashboard_api import import_character_payload
    from companion.equipment.loadout_cli import load_loadout
    from companion.equipment.schema import SlotType

    first = {"items": [boots_item(), gloves_item()]}
    second = {"items": [boots_item()]}
    import_character_payload({"character_id": "T", "character_data": first, "overwrite": True}, tmp_path)
    import_character_payload({"character_id": "T", "character_data": second, "overwrite": True}, tmp_path)
    lo = load_loadout(tmp_path, "T")
    assert lo.get_slot(SlotType.GLOVES) is None
    assert lo.get_slot(SlotType.BOOTS) is not None


def test_import_keeps_manual_facts_and_marks_others_stale(tmp_path: Path) -> None:
    from companion.dashboard_api import import_character_payload
    from companion.equipment.baseline import BaselineSource, CharacterFact, CharacterStatBaseline
    from companion.equipment.baseline_cli import load_baseline, save_baseline
    from companion.state.provenance import VerificationState

    base = CharacterStatBaseline.create_empty(character_id="T", anchored_loadout_revision=1)
    base.life = CharacterFact[int].create(500, source=BaselineSource.MANUAL_USER_INPUT)
    base.raw_fire_res = CharacterFact[int].create(30, source=BaselineSource.GGG_OFFICIAL_API)
    save_baseline(tmp_path, base)
    import_character_payload({"character_id": "T", "character_data": {"items": [boots_item()]}}, tmp_path)
    after = load_baseline(tmp_path, "T")
    assert after.life.value == 500 and after.life.source == BaselineSource.MANUAL_USER_INPUT
    assert after.raw_fire_res.value == 30 and after.raw_fire_res.verification == VerificationState.STALE


def test_second_import_keeps_stale_facts_and_manual_facts(tmp_path: Path) -> None:
    from companion.dashboard_api import import_character_payload
    from companion.equipment.baseline import BaselineSource, CharacterFact, CharacterStatBaseline
    from companion.equipment.baseline_cli import load_baseline, save_baseline
    from companion.state.provenance import VerificationState

    base = CharacterStatBaseline.create_empty(character_id="T", anchored_loadout_revision=1)
    base.life = CharacterFact[int].create(500, source=BaselineSource.MANUAL_USER_INPUT)
    base.raw_fire_res = CharacterFact[int].create(30, source=BaselineSource.GGG_OFFICIAL_API)
    save_baseline(tmp_path, base)
    req = {"character_id": "T", "character_data": {"items": [boots_item()]}}
    import_character_payload(req, tmp_path)
    import_character_payload(req, tmp_path)
    after = load_baseline(tmp_path, "T")
    assert after.life.value == 500 and after.life.source == BaselineSource.MANUAL_USER_INPUT
    assert after.raw_fire_res.value == 30 and after.raw_fire_res.verification == VerificationState.STALE


def test_import_same_gear_keeps_manual_fact_verified_changed_gear_stales_it(tmp_path: Path) -> None:
    from companion.dashboard_api import import_character_payload
    from companion.equipment.baseline import BaselineSource, CharacterFact
    from companion.equipment.baseline_cli import load_baseline, save_baseline
    from companion.state.provenance import VerificationState

    req = {"character_id": "T", "character_data": {"items": [boots_item()]}}
    import_character_payload(req, tmp_path)
    base = load_baseline(tmp_path, "T")
    base.life = CharacterFact[int].create(500, source=BaselineSource.MANUAL_USER_INPUT)
    save_baseline(tmp_path, base)
    import_character_payload(req, tmp_path)
    assert load_baseline(tmp_path, "T").life.verification == VerificationState.VERIFIED
    import_character_payload(
        {"character_id": "T", "character_data": {"items": [boots_item(), gloves_item()]}}, tmp_path
    )
    after = load_baseline(tmp_path, "T")
    assert after.life.value == 500 and after.life.verification == VerificationState.STALE


def test_get_current_raw_converts_pob_session_text(tmp_path: Path) -> None:
    from companion.dashboard_api import get_current_raw

    eq = json.loads((PROJECT_ROOT / "tests" / "fixtures" / "pob" / "get_equipped.json").read_text(encoding="utf-8"))
    sess = MagicMock()
    sess.get_equipped_item.side_effect = lambda s: eq.get(s, {"equipped": False})
    raw = get_current_raw(tmp_path, "T", "helmet", sess)
    assert raw.startswith("Item Class: Helmets") and "Implicits:" not in raw and "{" not in raw


def test_get_current_raw_falls_back_to_loadout_on_bad_pob_text(tmp_path: Path) -> None:
    from companion.dashboard_api import get_current_raw
    from companion.equipment.loadout import EquippedLoadout
    from companion.equipment.loadout_cli import save_loadout
    from companion.equipment.parser import parse_item_text
    from companion.equipment.schema import SlotType

    lo = EquippedLoadout.create_draft(character_id="T")
    lo.transition_slot(SlotType.HELMET, parse_item_text(SAMPLE_BOOTS_TEXT.replace("Boots", "Helmets"), target_slot=SlotType.HELMET))
    lo.finalize(loadout_id="x")
    save_loadout(tmp_path, lo)
    sess = MagicMock()
    sess.get_equipped_item.return_value = {"equipped": True, "raw": "garbage"}
    assert "Brimstone Greaves" in get_current_raw(tmp_path, "T", "helmet", sess)


# --- evaluate_item_payload on the guide-aware pipeline (evaluation.evaluate) ---------------------------------

from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta  # noqa: E402
from tests.unit.equipment.test_evaluation import (  # noqa: E402
    FUB,
    Failing,
    Ring2Empty,
    Stub,
    _install,
    _item,
    _write_char,
)

BOOTS = _item("Boots", "Wool Shoes", ["+30 to maximum Life", "+10% to Cold Resistance"], name="Brimstone Greaves")
RING = _item("Rings", "Iron Ring", ["+30 to maximum Life", "+10% to Cold Resistance"], name="Gold Ring")
CROSSBOW = _item("Crossbows", "Tense Crossbow", ["+40 to maximum Life"], name="Dire Core")
WAND = _item("Wands", "Bone Wand", ["+40 to maximum Life"], name="Arcane Wand")
BOW = _item("Bows", "Short Bow", ["+40 to maximum Life"], name="Pain Branch")
BODY = _item("Body Armours", "Shrouded Vest", ["+5.8 Life Regeneration per second"], name="Maelstrom Keep")


class Tracking(Stub):
    def __init__(self) -> None:
        self.measured: list[str] = []

    def measure(self, slot, raw, candidate_id, **kw):
        self.measured.append(slot)
        return super().measure(slot, raw, candidate_id, **kw).model_copy(update={"dps_delta": 50.0})


class BadBody(Stub):
    level = 19

    def measure(self, slot, raw, candidate_id, **kw):
        return PobEquipmentDelta(
            slot=slot, candidate_id=candidate_id, candidate_name="Maelstrom Keep", life_delta=-7,
            fire_res_delta=-15, lightning_res_delta=-4, armour_delta=82, ehp_before=1000.0, ehp_after=983.2,
            dps_before=100.0, dps_after=100.0, res_before={"fire": 75}, res_after={"fire": 60},
        )

    def get_current_item_name(self, slot):
        return "Glyph Pelt"


def _payload(text, **kw):
    # "stage"/"guide" are legacy UI fields the server must ignore.
    return {"raw_text": text, "character_id": "BOMSHAK", "stage": "lvl 1-14", "guide": "ignored", **kw}


@pytest.fixture
def fub(tmp_path: Path) -> Path:
    _install(tmp_path, FUB, char="BOMSHAK", level=20)
    return tmp_path


def test_evaluate_item_payload_success_shape(fub: Path) -> None:
    res = evaluate_item_payload(_payload(BOOTS), runtime_dir=fub, pob_session=Stub())
    assert res["success"] is True
    assert (res["item_name"], res["base_type"], res["slot"], res["pob_slot"]) == ("Brimstone Greaves", "Wool Shoes", "boots", "Boots")
    assert res["verdict"] == "EQUIP_NOW" and res["engine"] == "pob2"
    assert res["is_weapon"] is False and res["recommended_slot"] == "Boots"
    assert isinstance(res["gains"], list) and isinstance(res["trade_offs"], list)
    assert res["reason"] and res["formatted_report"].startswith("EQUIP_NOW")
    assert res["guide"]["stage_title"] == "lvl 15-32" and res["per_slot"] and "delta" not in res["per_slot"][0]
    json.dumps(res)  # response must be JSON-serialisable


def test_evaluate_item_payload_requested_slot_respected(fub: Path) -> None:
    res = evaluate_item_payload(_payload(RING, slot="ring2"), runtime_dir=fub, pob_session=Stub())
    assert res["success"] is True and res["slot"] == "ring2" and res["pob_slot"] == "Ring 2"


def test_evaluate_item_payload_routes_set2_main_hand(tmp_path: Path) -> None:
    _write_char(tmp_path, "BOMSHAK", level=20)  # no guide: a one-hand weapon may go to either weapon set
    sess = Tracking()
    res = evaluate_item_payload(_payload(WAND, slot="set2_main_hand"), runtime_dir=tmp_path, pob_session=sess)
    assert res["success"] is True and res["slot"] == "set2_main_hand" and res["is_weapon"] is True
    assert sess.measured == ["Weapon 1 Swap"]


def test_evaluate_item_payload_routes_off_hand_to_weapon_2(tmp_path: Path) -> None:
    _write_char(tmp_path, "BOMSHAK", level=20)
    sess = Tracking()
    res = evaluate_item_payload(_payload(WAND, slot="off_hand"), runtime_dir=tmp_path, pob_session=sess)
    assert res["success"] is True and res["slot"] == "off_hand"
    assert sess.measured == ["Weapon 2"]


def test_evaluate_item_payload_dual_ring_picks_empty_slot(fub: Path) -> None:
    res = evaluate_item_payload(_payload(RING), runtime_dir=fub, pob_session=Ring2Empty())
    assert res["success"] is True and res["pob_slot"] == "Ring 2" and res["slot"] == "ring2"
    assert {s["slot"] for s in res["per_slot"]} == {"Ring 1", "Ring 2"}


def test_weapon_class_absent_from_guide_is_rejected(fub: Path) -> None:
    res = evaluate_item_payload(_payload(BOW), runtime_dir=fub, pob_session=Stub())
    assert res["verdict"] == "REJECT" and "Senjata tidak dipakai guide" in res["reason"]
    assert res["safety"] and res["is_weapon"] is True


def test_weapon_class_in_guide_is_measured(fub: Path) -> None:
    res = evaluate_item_payload(_payload(CROSSBOW), runtime_dir=fub, pob_session=Tracking())
    assert res["engine"] == "pob2" and res["safety"] == [] and res["is_weapon"] is True
    assert res["dps_delta"] == pytest.approx(50.0)  # PoB2 absolute DPS gain


def test_evaluate_item_payload_includes_zone_aware_tactical_advice(fub: Path) -> None:
    res = evaluate_item_payload(_payload(BODY, zone="G2_1"), runtime_dir=fub, pob_session=BadBody())
    assert res["success"] is True and res["verdict"] == "REJECT"
    t_adv = res["tactical_advice"]
    assert "TAHAN" in t_adv["verdict_badge"] or "\U0001f6d1" in t_adv["verdict_badge"]
    assert "Vastiri" in t_adv["zone_name"] or "G2_1" in t_adv["zone_name"]
    assert len(t_adv["actionable_recommendation"]) > 0


def test_evaluate_item_payload_resolves_real_current_item_name(fub: Path) -> None:
    from companion.equipment.loadout import EquippedLoadout
    from companion.equipment.loadout_cli import save_loadout
    from companion.equipment.parser import parse_item_text
    from companion.equipment.schema import SlotType

    lo = EquippedLoadout.create_draft(character_id="BOMSHAK")
    lo.transition_slot(SlotType.GLOVES, parse_item_text(
        "Item Class: Gloves\nRarity: Rare\nPlague Claw\nSpined Bracers\n--------\nArmour: 40\n--------\n+30 to Armour\n",
        target_slot=SlotType.GLOVES,
    ))
    lo.finalize(loadout_id="test")
    save_loadout(fub, lo)
    gloves = _item("Gloves", "Stocky Mitts", ["+43 to Armour", "+18% to Fire Resistance"], name="Horror Grip")
    res = evaluate_item_payload(_payload(gloves, zone="G2_1"), runtime_dir=fub, pob_session=None)
    assert res["item_name"] == "Horror Grip"
    assert res["current_item_name"] == "Plague Claw" and res["current_item_base_type"] == "Spined Bracers"


def test_evaluate_item_payload_stamps_evaluated_at(fub: Path) -> None:
    res = evaluate_item_payload(_payload(BOOTS), runtime_dir=fub, pob_session=Stub())
    assert isinstance(res["evaluated_at"], str) and len(res["evaluated_at"]) > 10


def test_evaluate_item_payload_pob2_failure_falls_back_with_engine_tag(fub: Path) -> None:
    res = evaluate_item_payload(_payload(BOOTS), runtime_dir=fub, pob_session=Failing())
    assert res["success"] is True and res["engine"] == "heuristic" and res["engine_reason"]


def test_evaluate_item_payload_empty_input() -> None:
    assert "empty" in evaluate_item_payload({"raw_text": ""}, runtime_dir=PROJECT_ROOT / "runtime")["error"].lower()


def test_evaluate_item_payload_malformed_input(tmp_path: Path) -> None:
    assert "error" in evaluate_item_payload({"raw_text": "Random gibberish that is not an item"}, runtime_dir=tmp_path)


def test_evaluate_item_payload_bad_locked_slot_is_error(fub: Path) -> None:
    assert "error" in evaluate_item_payload(_payload(BOOTS, slot="helmet"), runtime_dir=fub, pob_session=Stub())


def test_auto_clipboard_resolves_zone_and_source(fub: Path, monkeypatch: Any) -> None:
    import companion.dashboard_api as d_api

    (fub / "characters" / "BOMSHAK.json").write_text(
        json.dumps({"level": {"value": 19}, "current_zone": {"value": "G2_1"}}), encoding="utf-8"
    )
    d_api._LAST_SEEN_CLIPBOARD = ""
    monkeypatch.setattr(d_api, "get_clipboard_text", lambda: BODY)
    seen = []
    orig = d_api.evaluate

    def spy(*a, **kw):
        seen.append(kw["source"])
        return orig(*a, **kw)

    monkeypatch.setattr(d_api, "evaluate", spy)
    res = d_api.check_auto_clipboard(fub, "BOMSHAK", pob_session=BadBody())
    assert res["has_new_item"] is True and res["raw_text"] == BODY.strip() and res["verdict"] == "REJECT"
    assert "Vastiri" in res["tactical_advice"]["zone_name"] and seen == ["auto"]


def test_check_auto_clipboard_passes_zone(fub: Path, monkeypatch: Any) -> None:
    import companion.dashboard_api as d_api

    d_api._LAST_SEEN_CLIPBOARD = ""
    monkeypatch.setattr(d_api, "get_clipboard_text", lambda: BOOTS)
    zones = []

    def spy(*a, **kw):
        zones.append(kw["zone"])
        raise ValueError("stop")

    monkeypatch.setattr(d_api, "evaluate", spy)
    res = d_api.check_auto_clipboard(fub, "BOMSHAK", zone="vastiri_outskirts")
    assert zones == ["vastiri_outskirts"] and res["has_new_item"] is True and "error" in res


def test_check_auto_clipboard_reevaluates_on_context_change(fub: Path, monkeypatch: Any) -> None:
    import companion.dashboard_api as d_api

    d_api._LAST_SEEN_CLIPBOARD = ""
    monkeypatch.setattr(d_api, "get_clipboard_text", lambda: BOOTS)
    assert d_api.check_auto_clipboard(fub, char_id="BOMSHAK", pob_session=Stub())["has_new_item"] is True
    assert d_api.check_auto_clipboard(fub, char_id="BOMSHAK", pob_session=Stub())["has_new_item"] is False
    assert d_api.check_auto_clipboard(fub, char_id="Varashta", pob_session=Stub())["has_new_item"] is True
    from companion.builds.store import set_assignment
    set_assignment(fub, "Varashta", FUB, "all")
    assert d_api.check_auto_clipboard(fub, char_id="Varashta", pob_session=Stub())["has_new_item"] is True


def test_evaluate_item_payload_unexpected_failure_returns_error(fub: Path, monkeypatch: Any) -> None:
    import companion.dashboard_api as d_api

    def boom(*a, **kw):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(d_api, "evaluate", boom)
    assert d_api.evaluate_item_payload(_payload(BOOTS), runtime_dir=fub) == {"error": "Evaluation error: kaboom"}
