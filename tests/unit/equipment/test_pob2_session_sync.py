"""Unit tests for PoB2 Session Equipment Synchronization & Lifecycle (TDD RED).

Validates:
1. `Pob2EquipmentSession.equip_item()` updates the active baseline XML via export_xml,
   updates equipped_items for that slot, and refreshes defenses_before and stats_before.
2. Subsequent `simulate_item()` evaluations compare against the newly equipped item,
   not the initial baseline item.
3. `Pob2EquipmentSession.sync_character()` re-imports character and resets the baseline.
4. Auto-progression stage inference based on character level.
5. Invalidation or synchronization of global session in dashboard server.
"""

from __future__ import annotations

from typing import Any
import pytest

from companion.equipment.pob2_equipment_advisor import (
    Pob2EquipmentSession,
)
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.schema import SlotType


SKULL_WARD_RAW = """Item Class: Helmets
Rarity: Rare
Skull Ward
Visored Helm
--------
Armour: 75
Evasion Rating: 64
--------
Requirements:
Level: 16
--------
+21 to Armour
+18 to Evasion Rating
+7% to Fire Resistance
+9% to Lightning Resistance
+30 to Accuracy Rating
10% increased Light Radius
"""

KRAKEN_DOME_RAW = """Item Class: Helmets
Rarity: Rare
Kraken Dome
Rusted Greathelm
--------
Armour: 32
--------
Requirements:
Level: 6
--------
+20 to Maximum Life
+7% to Lightning Resistance
2.7 Life Regeneration per second
"""

BRIMSTONE_VEIL_RAW = """Item Class: Helmets
Rarity: Rare
Brimstone Veil
Hewn Mask
--------
Evasion: 70
Energy Shield: 32
--------
+32 to Evasion Rating
+11 to maximum Energy Shield
+12 to maximum Mana
"""


class SyncFakePobEngine:
    """Mock PoB engine supporting export_xml and equip_item state mutation."""

    def __init__(self):
        self.call_log: list[str] = []
        self.xml = "<PathOfBuilding><Build><Helmet>Brimstone Veil</Helmet></Build></PathOfBuilding>"
        self.equipped_items = {
            "Helmet": {"equipped": True, "name": "Brimstone Veil", "raw": BRIMSTONE_VEIL_RAW, "slot": "Helmet"}
        }
        self.defenses = {
            "Life": 300,
            "Armour": 50,
            "Evasion": 70,
            "EnergyShield": 32,
            "TotalEHP": 250.0,
        }
        self.stats = {
            "defense": {
                "FireResist": 0,
                "ColdResist": 0,
                "LightningResist": 0,
                "ChaosResist": 0,
                "MovementSpeed": 0.0,
            },
            "offense": {"CombinedDPS": 20.0},
        }

    def call(self, action: str, **kwargs: Any) -> dict[str, Any]:
        self.call_log.append(action)

        if action == "import_character":
            return {
                "className": "Mercenary",
                "level": 18,
                "xml": self.xml,
            }
        elif action == "import_build":
            self.xml = kwargs.get("xml", self.xml)
            return {"success": True}
        elif action == "export_xml":
            return {"xml": self.xml}
        elif action == "get_equipped":
            slot = kwargs.get("slot")
            return self.equipped_items.get(slot, {"equipped": False})
        elif action == "get_defenses":
            return dict(self.defenses)
        elif action == "calc_stats":
            return {
                "defense": dict(self.stats["defense"]),
                "offense": dict(self.stats["offense"]),
            }
        elif action == "equip_item":
            slot = kwargs.get("slot")
            raw = kwargs.get("raw", "")
            name = "Unknown Item"
            if "Skull Ward" in raw:
                name = "Skull Ward"
                self.defenses["Armour"] = 125
                self.defenses["Evasion"] = 134
                self.stats["defense"]["FireResist"] = 7
                self.stats["defense"]["LightningResist"] = 9
            elif "Kraken Dome" in raw:
                name = "Kraken Dome"
                self.defenses["Life"] = 320
                self.stats["defense"]["FireResist"] = 0
                self.stats["defense"]["LightningResist"] = 7

            self.equipped_items[slot] = {"equipped": True, "name": name, "raw": raw, "slot": slot}
            self.xml = f"<PathOfBuilding><Build><{slot}>{name}</{slot}></Build></PathOfBuilding>"
            return {"success": True}

        return {"success": True}


class SyncFakePoeApi:
    def fetch_character_raw(self, character_name: str) -> str:
        return f'{{"character": "{character_name}"}}'


def test_equip_item_mutates_active_pob_baseline_xml_and_equipped_cache():
    """Equipping an item must update baseline XML and equipped item cache."""
    engine = SyncFakePobEngine()
    api = SyncFakePoeApi()
    sess = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: engine,
        poe_api_client=api,
    )
    assert sess.initialize() is True
    assert sess.get_current_item_name("Helmet") == "Brimstone Veil"

    # Equip Skull Ward
    success = sess.equip_item("Helmet", SKULL_WARD_RAW)
    assert success is True
    assert sess.get_current_item_name("Helmet") == "Skull Ward"
    assert "<Helmet>Skull Ward</Helmet>" in sess.xml
    assert sess.defenses_before["Armour"] == 125
    assert sess.stats_before["defense"]["FireResist"] == 7

    # Subsequent simulate_item for Kraken Dome should compare against Skull Ward
    delta = sess.simulate_item("Helmet", KRAKEN_DOME_RAW, candidate_name="Kraken Dome")
    assert delta is not None
    assert delta.current_item_name == "Skull Ward"
    assert delta.candidate_name == "Kraken Dome"
    # Fire res drops from 7 to 0 -> -7
    assert delta.fire_res_delta == -7
    # Lightning res drops from 9 to 7 -> -2
    assert delta.lightning_res_delta == -2


def test_sync_character_reloads_from_api():
    """sync_character must re-fetch character data and reset baseline stats."""
    engine = SyncFakePobEngine()
    api = SyncFakePoeApi()
    sess = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: engine,
        poe_api_client=api,
    )
    assert sess.initialize() is True
    assert sess.get_current_item_name("Helmet") == "Brimstone Veil"

    # Engine external change (e.g. GGG API updated)
    engine.equipped_items["Helmet"] = {
        "equipped": True,
        "name": "Skull Ward",
        "raw": SKULL_WARD_RAW,
        "slot": "Helmet",
    }
    engine.xml = "<PathOfBuilding><Build><Helmet>Skull Ward</Helmet></Build></PathOfBuilding>"

    res = sess.sync_character()
    assert res is True
    assert sess.get_current_item_name("Helmet") == "Skull Ward"


def test_evaluate_item_payload_auto_infers_stage_from_pob_session_level(tmp_path: Path):
    """evaluate_item_payload should auto-advance stage if character level is higher than default."""
    from companion.dashboard_api import evaluate_item_payload

    engine = SyncFakePobEngine()
    api = SyncFakePoeApi()
    sess = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: engine,
        poe_api_client=api,
    )
    sess.initialize()
    sess.level = 18  # Character is level 18

    # Payload omits stage or passes default lvl 1-14
    payload = {
        "raw_text": KRAKEN_DOME_RAW,
        "character_id": "BOMSHAK",
        "stage": "lvl 1-14",
    }
    result = evaluate_item_payload(payload, runtime_dir=tmp_path, pob_session=sess)
    assert result.get("success") is True
    # The formatted report should reflect LEVELING_15_32 rather than LEVELING_1_14
    assert "LEVELING_15_32" in result.get("formatted_report", "")


def test_dashboard_server_equip_item_syncs_to_global_pob_session(monkeypatch, tmp_path: Path):
    """When /api/equip-item is called, _GLOBAL_POB_SESSION should equip the item directly."""
    from companion import dashboard_server

    engine = SyncFakePobEngine()
    api = SyncFakePoeApi()
    sess = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: engine,
        poe_api_client=api,
    )
    sess.initialize()
    monkeypatch.setattr(dashboard_server, "_GLOBAL_POB_SESSION", sess)

    # Simulate equip-item handler execution
    dashboard_server.sync_equipped_item_to_pob_session(
        character_id="BOMSHAK",
        slot="Helmet",
        raw_text=SKULL_WARD_RAW,
    )

    assert sess.get_current_item_name("Helmet") == "Skull Ward"


def test_infer_stage_from_level():
    """Level progression stages must be accurately inferred from character level."""
    from companion.equipment.fubgun_priorities import infer_stage_from_level

    assert infer_stage_from_level(1) == BuildProgressionStage.LEVELING_1_14
    assert infer_stage_from_level(14) == BuildProgressionStage.LEVELING_1_14
    assert infer_stage_from_level(15) == BuildProgressionStage.LEVELING_15_32
    assert infer_stage_from_level(18) == BuildProgressionStage.LEVELING_15_32
    assert infer_stage_from_level(32) == BuildProgressionStage.LEVELING_15_32
    assert infer_stage_from_level(33) == BuildProgressionStage.LEVELING_33_51
    assert infer_stage_from_level(52) == BuildProgressionStage.SWAP_52
    assert infer_stage_from_level(60) == BuildProgressionStage.LEVELING_53_68
    assert infer_stage_from_level(85) == BuildProgressionStage.LEVEL_85
    assert infer_stage_from_level(95) == BuildProgressionStage.ENDGAME
