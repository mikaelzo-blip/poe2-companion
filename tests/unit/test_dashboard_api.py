"""Unit tests for Dashboard API evaluation and server endpoints."""

from __future__ import annotations

import json
from pathlib import Path
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


def test_evaluate_item_payload_boots_success(tmp_path: Path) -> None:
    # Use isolated test runtime dir
    runtime_dir = tmp_path
    payload = {
        "raw_text": SAMPLE_BOOTS_TEXT,
        "character_id": "BOMSHAK",
        "stage": "lvl 1-14",
    }
    result = evaluate_item_payload(payload, runtime_dir=runtime_dir)
    assert result.get("success") is True
    assert result.get("item_name") == "Brimstone Greaves"
    assert result.get("base_type") == "Iron Greaves"
    assert result.get("slot") == "boots"
    assert "verdict" in result
    assert result.get("verdict") in ("INSUFFICIENT_DATA", "EQUIP_NOW", "CONDITIONAL_UPGRADE", "REJECT")
    assert "reason" in result
    assert isinstance(result.get("gains"), list)
    assert len(result.get("gains")) > 0
    assert any("+18 Life" in g for g in result["gains"])
    assert isinstance(result.get("trade_offs"), list)
    assert result.get("formatted_report") is not None


def test_evaluate_item_payload_weapon_success() -> None:
    runtime_dir = PROJECT_ROOT / "runtime"
    payload = {
        "raw_text": SAMPLE_WEAPON_TEXT,
        "character_id": "BOMSHAK",
        "stage": "lvl 1-14",
    }
    result = evaluate_item_payload(payload, runtime_dir=runtime_dir)
    assert result.get("success") is True
    assert result.get("item_name") == "Dire Core"
    assert "verdict" in result
    assert result.get("is_weapon") is True


def test_evaluate_item_payload_ring_success() -> None:
    runtime_dir = PROJECT_ROOT / "runtime"
    payload = {
        "raw_text": SAMPLE_RING_TEXT,
        "character_id": "BOMSHAK",
        "stage": "lvl 1-14",
    }
    result = evaluate_item_payload(payload, runtime_dir=runtime_dir)
    assert result.get("success") is True
    assert result.get("item_name") == "Gold Ring"
    assert "verdict" in result
    assert "Ring 1" in result.get("formatted_report", "")


def test_evaluate_item_payload_respects_requested_slot() -> None:
    runtime_dir = PROJECT_ROOT / "runtime"
    payload_ring2 = {
        "raw_text": SAMPLE_RING_TEXT,
        "character_id": "BOMSHAK",
        "stage": "lvl 1-14",
        "slot": "ring2",
    }
    result_ring2 = evaluate_item_payload(payload_ring2, runtime_dir=runtime_dir)
    assert result_ring2.get("success") is True
    assert result_ring2.get("slot") == "ring2"

    payload_set2 = {
        "raw_text": SAMPLE_WEAPON_TEXT,
        "character_id": "BOMSHAK",
        "stage": "lvl 1-14",
        "slot": "set2_main_hand",
    }
    result_set2 = evaluate_item_payload(payload_set2, runtime_dir=runtime_dir)
    assert result_set2.get("success") is True
    assert result_set2.get("slot") == "set2_main_hand"


def test_evaluate_item_payload_routes_set2_weapons_to_swap_slots(tmp_path: Path) -> None:
    from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta

    class TrackingPobSession:
        is_available = True

        def __init__(self) -> None:
            self.submitted_slots: list[str] = []
            self.simulated_slots: list[str] = []

        def submit_candidate(self, raw_text: str, candidate_name: str, slot: str) -> int:
            self.submitted_slots.append(slot)
            return 1

        def simulate_item(self, slot: str, raw_candidate: str, candidate_id: int, candidate_name: str):
            self.simulated_slots.append(slot)
            return PobEquipmentDelta(
                slot=slot,
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                dps_delta=5.0,
            )

    session = TrackingPobSession()
    result = evaluate_item_payload(
        {
            "raw_text": SAMPLE_WEAPON_TEXT,
            "character_id": "BOMSHAK",
            "stage": "lvl 1-14",
            "slot": "set2_main_hand",
        },
        runtime_dir=tmp_path,
        pob_session=session,
    )

    assert result.get("success") is True
    assert session.submitted_slots == ["Weapon 1 Swap"]
    assert session.simulated_slots == ["Weapon 1 Swap"]


def test_evaluate_item_payload_routes_off_hand_to_weapon_2(tmp_path: Path) -> None:
    from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta

    class TrackingPobSession:
        is_available = True

        def __init__(self) -> None:
            self.submitted_slots: list[str] = []
            self.simulated_slots: list[str] = []

        def submit_candidate(self, raw_text: str, candidate_name: str, slot: str) -> int:
            self.submitted_slots.append(slot)
            return 1

        def simulate_item(self, slot: str, raw_candidate: str, candidate_id: int, candidate_name: str):
            self.simulated_slots.append(slot)
            return PobEquipmentDelta(
                slot=slot,
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                dps_delta=2.0,
            )

    session = TrackingPobSession()
    result = evaluate_item_payload(
        {
            "raw_text": SAMPLE_WEAPON_TEXT,
            "character_id": "BOMSHAK",
            "stage": "lvl 1-14",
            "slot": "off_hand",
        },
        runtime_dir=tmp_path,
        pob_session=session,
    )

    assert result.get("success") is True
    assert session.submitted_slots == ["Weapon 2"]
    assert session.simulated_slots == ["Weapon 2"]


def test_evaluate_item_payload_pob2_dual_ring_recommendation(tmp_path: Path) -> None:
    from companion.equipment.pob2_equipment_advisor import DualRingSimulationResult, PobEquipmentDelta

    class RingPobSession:
        is_available = True

        def submit_candidate(self, raw_text: str, candidate_name: str, slot: str) -> int:
            return 1

        def simulate_ring_candidate(self, raw_candidate: str, candidate_id: int, candidate_name: str):
            return DualRingSimulationResult(
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                ring1_delta=PobEquipmentDelta(
                    slot="Ring 1",
                    candidate_id=candidate_id,
                    candidate_name=candidate_name,
                    life_delta=25,
                    cold_res_delta=15,
                    ehp_delta=30.0,
                ),
                ring2_delta=PobEquipmentDelta(
                    slot="Ring 2",
                    candidate_id=candidate_id,
                    candidate_name=candidate_name,
                    life_delta=-30,
                    fire_res_delta=-20,
                    ehp_delta=-40.0,
                ),
            )

        def is_slot_empty(self, slot: str) -> bool:
            return False

    session = RingPobSession()
    result = evaluate_item_payload(
        {
            "raw_text": SAMPLE_RING_TEXT,
            "character_id": "BOMSHAK",
            "stage": "lvl 1-14",
            "slot": "ring1",
        },
        runtime_dir=tmp_path,
        pob_session=session,
    )

    assert result.get("success") is True
    assert result.get("verdict") == "EQUIP_NOW"
    assert result.get("recommended_slot") == "Ring 1"
    assert "Recommended placement: Ring 1" in result.get("reason", "")
    assert "Vs Ring 1" in result.get("formatted_report", "")


def test_evaluate_item_payload_body_armour_and_amulet() -> None:
    runtime_dir = PROJECT_ROOT / "runtime"
    payload_body = {
        "raw_text": SAMPLE_BODY_ARMOUR_TEXT,
        "character_id": "BOMSHAK",
        "stage": "lvl 1-14",
        "slot": "body_armour",
    }
    result_body = evaluate_item_payload(payload_body, runtime_dir=runtime_dir)
    assert result_body.get("success") is True
    assert result_body.get("item_name") == "Dragon Carapace"
    assert result_body.get("slot") == "body_armour"

    payload_amulet = {
        "raw_text": SAMPLE_AMULET_TEXT,
        "character_id": "BOMSHAK",
        "stage": "lvl 1-14",
        "slot": "amulet",
    }
    result_amulet = evaluate_item_payload(payload_amulet, runtime_dir=runtime_dir)
    assert result_amulet.get("success") is True
    assert result_amulet.get("item_name") == "Beast Medallion"
    assert result_amulet.get("slot") == "amulet"


def test_evaluate_item_payload_empty_input() -> None:
    runtime_dir = PROJECT_ROOT / "runtime"
    result = evaluate_item_payload({"raw_text": ""}, runtime_dir=runtime_dir)
    assert "error" in result
    assert "empty" in result["error"].lower()


def test_evaluate_item_payload_malformed_input() -> None:
    runtime_dir = PROJECT_ROOT / "runtime"
    result = evaluate_item_payload({"raw_text": "Random gibberish that is not an item"}, runtime_dir=runtime_dir)
    assert "error" in result


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
                assert len(guides_body["guides"]) >= 2

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

            # 5. Test GET static assets (HTML, CSS, JS)
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
                assert resp.status == 200
                html_text = resp.read().decode("utf-8")
                assert "compare-history-container" in html_text
                assert "TARGET LOADOUT SLOT" in html_text

            with urllib.request.urlopen(f"http://127.0.0.1:{port}/app.js", timeout=5) as resp:
                assert resp.status == 200
                js_text = resp.read().decode("utf-8")
                assert "SLOT_LABELS" in js_text
                assert "recordSlotComparison" in js_text

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


def test_evaluate_item_payload_pob2_rejects_incompatible_bow(tmp_path: Path) -> None:
    class MockAvailablePobSession:
        is_available = True
        xml = "<PathOfBuilding></PathOfBuilding>"
        engine = MagicMock()

        def submit_candidate(self, raw_text: str, candidate_name: str, slot: str) -> int:
            return 42

        def get_current_item_name(self, slot: str) -> str:
            return ""

    bow_text = """Item Class: Bows
Rarity: Rare
Pain Branch
Short Bow
--------
Physical Damage: 12-24
Attacks per Second: 1.30
--------
Requirements:
Level: 10
Dex: 25
--------
Adds 2 to 5 Physical Damage"""

    session = MockAvailablePobSession()
    res = evaluate_item_payload(
        {
            "raw_text": bow_text,
            "character_id": "BOMSHAK",
            "stage": "lvl 1-14",
        },
        runtime_dir=tmp_path,
        pob_session=session,
    )

    assert res.get("success") is True
    assert res.get("verdict") == "REJECT"
    assert "bow" in res.get("reason", "").lower() or "incompatible" in res.get("reason", "").lower()


def test_evaluate_item_payload_includes_zone_aware_tactical_advice(tmp_path: Path) -> None:
    class MockAvailablePobSession:
        is_available = True
        xml = "<PathOfBuilding></PathOfBuilding>"
        engine = MagicMock()
        level = 19

        def submit_candidate(self, raw_text: str, candidate_name: str, slot: str) -> int:
            return 99

        def simulate_item(self, slot: str, raw_candidate: str, candidate_id: int, candidate_name: str):
            from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
            return PobEquipmentDelta(
                slot="Body Armour",
                candidate_id=candidate_id,
                candidate_name="Maelström Keep",
                current_item_name="Glyph Pelt",
                life_delta=-7,
                fire_res_delta=-15,
                lightning_res_delta=-4,
                armour_delta=82,
                ehp_delta=-16.80,
            )

        def get_current_item_name(self, slot: str) -> str:
            return "Glyph Pelt"

    session = MockAvailablePobSession()
    res = evaluate_item_payload(
        {
            "raw_text": "Item Class: Body Armours\nRarity: Rare\nMaelström Keep\nShrouded Vest\nEvasion Rating: 209\n5.8 Life Regeneration per second\n",
            "character_id": "BOMSHAK",
            "stage": "lvl 15-32",
            "zone": "G2_1",
        },
        runtime_dir=tmp_path,
        pob_session=session,
    )

    assert res.get("success") is True
    assert res.get("verdict") == "REJECT"
    assert "tactical_advice" in res
    t_adv = res["tactical_advice"]
    assert "🛑" in t_adv["verdict_badge"] or "TAHAN" in t_adv["verdict_badge"]
    assert "Vastiri" in t_adv["zone_name"] or "G2_1" in t_adv["zone_name"]
    assert "5.8" in t_adv["sustain_evaluation"] or "Regen" in t_adv["sustain_evaluation"]
    assert len(t_adv["actionable_recommendation"]) > 0


def test_auto_clipboard_resolves_character_zone_from_file(tmp_path: Path) -> None:
    from companion.dashboard_api import check_auto_clipboard
    char_dir = tmp_path / "characters"
    char_dir.mkdir(parents=True, exist_ok=True)
    (char_dir / "BOMSHAK.json").write_text(
        json.dumps({
            "character_id": "BOMSHAK",
            "level": {"value": 19},
            "current_zone": {"value": "G2_1"},
        }),
        encoding="utf-8",
    )

    class MockPobSession:
        is_available = True
        xml = "<PathOfBuilding></PathOfBuilding>"
        engine = MagicMock()
        level = 19

        def submit_candidate(self, raw_text: str, candidate_name: str, slot: str) -> int:
            return 1

        def simulate_item(self, slot: str, raw_candidate: str, candidate_id: int, candidate_name: str):
            from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
            return PobEquipmentDelta(
                slot="Body Armour",
                candidate_id=candidate_id,
                candidate_name="Maelström Keep",
                current_item_name="Glyph Pelt",
                life_delta=-7,
                fire_res_delta=-15,
                lightning_res_delta=-4,
                armour_delta=82,
                ehp_delta=-16.80,
            )

        def get_current_item_name(self, slot: str) -> str:
            return "Glyph Pelt"

    item_text = "Item Class: Body Armours\nRarity: Rare\nMaelström Keep\nShrouded Vest\nEvasion Rating: 209\n"
    with patch("companion.dashboard_api.get_clipboard_text", return_value=item_text):
        # Reset last seen
        import companion.dashboard_api
        companion.dashboard_api._LAST_SEEN_CLIPBOARD = ""

        res = check_auto_clipboard(
            runtime_dir=tmp_path,
            char_id="BOMSHAK",
            stage_str="lvl 15-32",
            pob_session=MockPobSession(),
        )

        assert res.get("has_new_item") is True
        assert res.get("verdict") == "REJECT"
        assert "tactical_advice" in res
        assert "Vastiri" in res["tactical_advice"]["zone_name"]


def test_evaluate_weapon_and_ring_include_tactical_advice(tmp_path: Path) -> None:
    """Verify that weapon and ring evaluations also contain tactical_advice across the board."""
    char_file = tmp_path / "characters" / "BOMSHAK.json"
    char_file.parent.mkdir(parents=True, exist_ok=True)
    char_file.write_text(
        json.dumps({
            "character_id": "BOMSHAK",
            "level": {"value": 19},
            "current_zone": {"value": "G2_1"},
        }),
        encoding="utf-8",
    )

    class MockPobWeaponSession:
        is_available = True
        xml = "<PathOfBuilding></PathOfBuilding>"
        level = 19

        def submit_candidate(self, raw_text: str, candidate_name: str, slot: str) -> int:
            return 1

        def simulate_item(self, slot: str, raw_candidate: str, candidate_id: int, candidate_name: str):
            from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
            return PobEquipmentDelta(
                slot="Weapon 1",
                candidate_id=candidate_id,
                candidate_name="Inferior Bow",
                current_item_name="Current Crossbow",
                dps_delta=-12.5,
                life_delta=0,
            )

        def get_current_item_name(self, slot: str) -> str:
            return "Current Crossbow"

    payload = {
        "raw_text": "Item Class: Bows\nRarity: Magic\nInferior Bow\nPhysical Damage: 5-10\n",
        "character_id": "BOMSHAK",
        "stage": "lvl 15-32",
    }
    res = evaluate_item_payload(payload, runtime_dir=tmp_path, pob_session=MockPobWeaponSession())
    assert res.get("success") is True
    assert res.get("verdict") == "REJECT"
    assert "tactical_advice" in res
    assert "senjata" in res["tactical_advice"]["tactical_headline"].lower()


def test_get_account_characters(tmp_path: Path) -> None:
    from companion.dashboard_api import get_account_characters

    # Create dummy oauth_status.json in sibling folder
    mock_pob_dir = tmp_path / "mock_pob"
    mock_pob_dir.mkdir(parents=True, exist_ok=True)
    oauth_file = mock_pob_dir / "oauth_status.json"
    oauth_file.write_text(
        json.dumps({
            "status": "SUCCESS",
            "characters": [
                {"name": "BOMSHAK", "level": 19, "class": "Mercenary", "league": "Forbidden Rites"},
                {"name": "DaisyofWar", "level": 71, "class": "Witch3", "league": "Standard"},
            ],
        }),
        encoding="utf-8",
    )

    with patch("companion.dashboard_api.resolve_pob2_backend_path", return_value=mock_pob_dir):
        res = get_account_characters(account_name="mikaelzo#5674", runtime_dir=tmp_path)
        assert res.get("account") == "mikaelzo#5674"
        assert "characters" in res
        char_names = [c["name"] for c in res["characters"]]
        assert "BOMSHAK" in char_names
        assert "DaisyofWar" in char_names
        assert res.get("active_character_id") == "BOMSHAK"


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


def test_get_available_guides() -> None:
    from companion.dashboard_api import get_available_guides

    res = get_available_guides()
    assert "guides" in res
    guide_ids = [g["id"] for g in res["guides"]]
    assert "fubgun_flameblast" in guide_ids
    assert "generic_pob2" in guide_ids


def test_evaluate_item_payload_generic_pob2_allows_non_fubgun_weapon(tmp_path: Path) -> None:
    from companion.dashboard_api import evaluate_item_payload

    # Create a Witch character profile
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

    class MockWitchPobSession:
        is_available = True
        character_name = "DaisyofWar"
        level = 71

        def submit_candidate(self, raw_text: str, candidate_name: str, slot: str) -> int:
            return 1

        def simulate_item(self, slot: str, raw_candidate: str, candidate_id: int, candidate_name: str):
            from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
            return PobEquipmentDelta(
                slot="Weapon 1",
                candidate_id=candidate_id,
                candidate_name="Arcane Wand",
                current_item_name="Old Wand",
                dps_delta=250.0,
                life_delta=20.0,
                ehp_delta=150.0,
            )

        def get_current_item_name(self, slot: str) -> str:
            return "Old Wand"

    wand_raw = """Item Class: Wands
Rarity: Rare
Arcane Wand
Bone Wand
--------
Requirements:
Level: 65
Int: 140
--------
Adds 20 to 45 Fire Damage to Spells
+30 to maximum Life
+1 to Level of all Fire Spell Skill Gems
"""
    payload = {
        "raw_text": wand_raw,
        "character_id": "DaisyofWar",
        "guide": "generic_pob2",
    }
    res = evaluate_item_payload(payload, runtime_dir=tmp_path, pob_session=MockWitchPobSession())
    assert res.get("success") is True
    # In generic PoB2 mode, dps_delta=+250 should NOT be rejected by Fubgun crossbow router!
    assert res.get("verdict") in ("EQUIP_NOW", "CONDITIONAL_UPGRADE")
    assert res.get("verdict") != "REJECT"
    assert "Fubgun" not in res.get("policy_verdict", "")


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







