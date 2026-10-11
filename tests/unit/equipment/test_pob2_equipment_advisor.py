"""Unit tests for generic PoB2 Equipment Advisor foundation.

Validates:
1. Canonical slot validation: normalize and validate equipment slots; fail closed on unknown slots.
2. Thread-safe bookkeeping: request ID allocation and stale checks use safe synchronization
   independent from the expensive PoB engine lock.
3. XML slot manipulation, metric delta calculation, and guide XML measurement.
"""

from __future__ import annotations

import logging
import time
from typing import Any
import pytest

from companion.equipment.pob2_equipment_advisor import (
    CANONICAL_EQUIPMENT_SLOTS,
    EngineError,
    POB2_PRODUCTION_SLOTS,
    POB2_PRODUCTION_WEAPON_SLOTS,
    Pob2EquipmentSession,
    PobEquipmentDelta,
    _clear_slots_in_xml,
    normalize_and_validate_pob_slot,
)
from companion.equipment.schema import SlotType


BRIMSTONE_VEIL_RAW = """Item Class: Helmets
Rarity: Rare
Brimstone Veil
Hewn Mask
--------
Evasion: 70
Energy Shield: 32
--------
Requirements:
Level: 17
Dex: 20
Int: 20
--------
Item Level: 17
--------
+32 to Evasion Rating
+11 to maximum Energy Shield
34% increased Evasion and Energy Shield
+36 to Accuracy Rating
+12 to maximum Mana
9% increased Rarity of Items found
3.9 Life Regeneration per second
10% increased Light Radius
"""

KRAKEN_DOME_RAW = """Item Class: Helmets
Rarity: Rare
Kraken Dome
Soldier Greathelm
--------
Armour: 45
--------
Requirements:
Level: 15
Str: 22
--------
Item Level: 19
--------
+20 to maximum Life
+7% to Lightning Resistance
1.2 Life Regenerated per second
"""


class FakePobEngine:
    """Mock PoB engine matching the JSON protocol of pob_mcp.engine.PobEngine."""

    def __init__(self, simulate_delay: float = 0.0):
        self.simulate_delay = simulate_delay
        self.call_log: list[str] = []
        self.equipped_helmet = {
            "equipped": True,
            "name": "Brimstone Veil",
            "raw": BRIMSTONE_VEIL_RAW,
        }
        self.defenses_before = {
            "Life": 361,
            "Armour": 253,
            "Evasion": 70,
            "EnergyShield": 32,
            "TotalEHP": 289.46,
        }
        self.stats_before = {
            "defense": {
                "FireResist": -35,
                "ColdResist": -50,
                "LightningResist": -43,
                "ChaosResist": 0,
                "MovementSpeed": 100.0,
            },
            "offense": {
                "CombinedDPS": 29.07,
            },
        }
        self.defenses_after = {
            "Life": 381,
            "Armour": 263,
            "Evasion": 70,
            "EnergyShield": 0,
            "TotalEHP": 296.20,
        }
        self.stats_after = {
            "defense": {
                "FireResist": -35,
                "ColdResist": -50,
                "LightningResist": -36,
                "ChaosResist": 0,
                "MovementSpeed": 120.0,
            },
            "offense": {
                "CombinedDPS": 27.25,
            },
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def call(self, action: str, **kwargs: Any) -> dict[str, Any]:
        self.call_log.append(action)

        if action == "import_character":
            return {
                "className": "Mercenary",
                "level": 17,
                "xml": "<PathOfBuilding><Build/></PathOfBuilding>",
            }
        elif action == "get_equipped":
            return self.equipped_helmet
        elif action == "get_defenses":
            return self.defenses_after if "equip_item" in self.call_log[-3:] else self.defenses_before
        elif action == "calc_stats":
            return self.stats_after if "equip_item" in self.call_log[-3:] else self.stats_before
        elif action == "equip_item":
            return {"success": True}
        elif action == "import_build":
            return {"success": True}
        return {"success": True}


class FakePoeApi:
    def fetch_character_raw(self, character_name: str) -> str:
        return f'{{"character": "{character_name}"}}'


class RecordingPobEngine(FakePobEngine):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def restart(self) -> None:
        self.call_log.append("restart")
        self.calls.append(("restart", {}))

    def call(self, action: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((action, kwargs))
        if action == "list_skills":
            return {"mainSocketGroup": 1, "groups": []}
        return super().call(action, **kwargs)


def test_clear_slots_in_xml_is_independent_of_attribute_order():
    xml = '<PathOfBuilding><ItemSet><Slot itemId="12" name="Weapon 2" active="true"/></ItemSet></PathOfBuilding>'

    cleared = _clear_slots_in_xml(xml, ["Weapon 2"])

    assert 'name="Weapon 2"' in cleared
    assert 'itemId="0"' in cleared


def test_build_delta_rejects_missing_metrics_instead_of_fabricating_zeroes():
    fake_engine = FakePobEngine()
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )

    with pytest.raises(ValueError, match="Missing PoB2 metrics"):
        session._build_delta(
            canonical_slot="Helmet",
            candidate_id=105,
            candidate_name="Partial Helmet",
            def_after={"Life": 320},
            stats_after={"defense": {}, "offense": {}},
            def_before={"Life": 300, "TotalEHP": 300.0},
            stats_before={"defense": {"FireResist": 10}, "offense": {"CombinedDPS": 20.0}},
        )


def test_build_delta_tolerates_missing_movement_speed_when_no_mods_in_pob2():
    """PoB2 omits MovementSpeed from defense table when EffectiveMovementSpeedMod is nil.

    _build_delta must not reject simulation or raise ValueError, defaulting movement delta to 0.0.
    """
    fake_engine = FakePobEngine()
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )

    def_before = {"Life": 300, "Armour": 100, "Evasion": 50, "EnergyShield": 20, "TotalEHP": 250.0}
    def_after = {"Life": 320, "Armour": 120, "Evasion": 50, "EnergyShield": 20, "TotalEHP": 270.0}
    stats_before = {
        "defense": {"FireResist": 10, "ColdResist": 10, "LightningResist": 10, "ChaosResist": 0},
        "offense": {"CombinedDPS": 20.0},
    }
    stats_after = {
        "defense": {"FireResist": 20, "ColdResist": 10, "LightningResist": 10, "ChaosResist": 0},
        "offense": {"CombinedDPS": 20.0},
    }

    delta = session._build_delta(
        canonical_slot="Helmet",
        candidate_id=1,
        candidate_name="Test Helm",
        def_after=def_after,
        stats_after=stats_after,
        def_before=def_before,
        stats_before=stats_before,
    )
    assert delta.movement_speed_delta == 0.0
    assert delta.fire_res_delta == 10
    assert delta.life_delta == 20


def test_generic_session_initialization_queries_all_core_equipped_items():
    """Pob2EquipmentSession queries and stores all core equipped slots on initialize."""
    fake_engine = FakePobEngine()
    fake_api = FakePoeApi()

    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=fake_api,
    )
    assert session.initialize() is True

    # Check that initialize called get_equipped for all production core slots
    for slot in ["Helmet", "Body Armour", "Gloves", "Boots", "Belt", "Amulet"]:
        assert slot in session.equipped_items
        assert session.get_current_item_name(slot) is not None


def test_canonical_slot_validation():
    """Valid equipment slots are normalized to canonical PoB slot names; invalid slots fail closed."""
    assert normalize_and_validate_pob_slot("Helmet") == "Helmet"
    assert normalize_and_validate_pob_slot("helmet") == "Helmet"
    assert normalize_and_validate_pob_slot("HELMET") == "Helmet"
    assert normalize_and_validate_pob_slot(SlotType.HELMET) == "Helmet"
    assert normalize_and_validate_pob_slot("Boots") == "Boots"
    assert normalize_and_validate_pob_slot(SlotType.BOOTS) == "Boots"
    assert normalize_and_validate_pob_slot("body_armour") == "Body Armour"
    assert normalize_and_validate_pob_slot("Body Armour") == "Body Armour"
    assert normalize_and_validate_pob_slot(SlotType.BODY_ARMOUR) == "Body Armour"
    assert normalize_and_validate_pob_slot("Gloves") == "Gloves"
    assert normalize_and_validate_pob_slot("Ring 1") == "Ring 1"
    assert normalize_and_validate_pob_slot("ring1") == "Ring 1"
    assert normalize_and_validate_pob_slot("Weapon 1") == "Weapon 1"

    # Invalid / unknown slots fail closed by raising ValueError
    with pytest.raises(ValueError, match="Unknown or unsupported equipment slot"):
        normalize_and_validate_pob_slot("spaceship")

    with pytest.raises(ValueError, match="Unknown or unsupported equipment slot"):
        normalize_and_validate_pob_slot("")

    with pytest.raises(ValueError, match="Unknown or unsupported equipment slot"):
        normalize_and_validate_pob_slot("invalid_slot")


def test_request_bookkeeping_thread_safety_independent_from_engine_lock():
    """Candidate ID generation and staleness checks must NOT block when the engine lock is held."""
    fake_engine = FakePobEngine()
    fake_api = FakePoeApi()

    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=fake_api,
    )
    assert session.initialize() is True

    # Acquire engine lock deliberately to simulate a long engine run
    session._engine_lock.acquire()
    try:
        # submit_candidate and is_stale must complete immediately without waiting for _engine_lock
        t0 = time.perf_counter()
        cid1 = session.submit_candidate(BRIMSTONE_VEIL_RAW)
        cid2 = session.submit_candidate(KRAKEN_DOME_RAW)
        stale1 = session.is_stale(cid1)
        stale2 = session.is_stale(cid2)
        elapsed = time.perf_counter() - t0

        assert cid1 == 1
        assert cid2 == 2
        assert stale1 is True
        assert stale2 is False
        # Must execute within milliseconds, not block on the acquired engine lock
        assert elapsed < 0.1
    finally:
        session._engine_lock.release()


def test_pob2_production_slots_includes_rings():
    """POB2_PRODUCTION_SLOTS must include Ring 1 and Ring 2 for production PoB2 evaluation."""
    assert "Ring 1" in POB2_PRODUCTION_SLOTS
    assert "Ring 2" in POB2_PRODUCTION_SLOTS


def test_pob2_production_slots_includes_weapons():
    """POB2_PRODUCTION_SLOTS must include canonical weapon slots for modular weapon subsystems."""
    for w_slot in ("Weapon 1", "Weapon 2", "Weapon 1 Swap", "Weapon 2 Swap"):
        assert w_slot in POB2_PRODUCTION_WEAPON_SLOTS
        assert w_slot in POB2_PRODUCTION_SLOTS


def test_measure_base_xml_uses_guide_xml_and_restores():
    """When base_xml is given, measure uses it without locking main skill and restores session baseline."""
    main_engine = RecordingPobEngine()
    sandbox_engine = RecordingPobEngine()
    engine_instances = iter([main_engine, sandbox_engine])

    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: next(engine_instances),
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True
    session.main_group = 1

    guide_xml = "<PathOfBuilding><GuideBuild/></PathOfBuilding>"
    candidate_id = session.submit_candidate(KRAKEN_DOME_RAW)
    sandbox_engine.calls.clear()

    delta = session.measure("Helmet", KRAKEN_DOME_RAW, candidate_id, base_xml=guide_xml)
    assert delta is not None

    import_calls = [kw["xml"] for action, kw in sandbox_engine.calls if action == "import_build"]
    skill_locks = [kw for action, kw in sandbox_engine.calls if action == "set_main_skill"]

    assert len(import_calls) >= 2
    assert "GuideBuild" in import_calls[0]
    assert 'useSecondWeaponSet="false"' in import_calls[0]
    assert len(skill_locks) == 0
    assert import_calls[-1] == session.xml


def _create_session(
    main_engine: RecordingPobEngine | None = None,
    sandbox_engine: RecordingPobEngine | None = None,
) -> tuple[Pob2EquipmentSession, RecordingPobEngine, RecordingPobEngine]:
    main = main_engine or RecordingPobEngine()
    sandbox = sandbox_engine or RecordingPobEngine()
    engine_instances = iter([main, sandbox])

    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: next(engine_instances),
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True
    session.main_group = 1
    return session, main, sandbox


def test_measure_superseded_mid_measure_returns_none():
    """is_stale flips to True between before and after readings; measure returns None and restores baseline."""
    session, _main_engine, sandbox_engine = _create_session()
    candidate_id = session.submit_candidate(KRAKEN_DOME_RAW)
    sandbox_engine.calls.clear()

    orig_call = sandbox_engine.call

    def call_with_supersede(action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "equip_item":
            session.submit_candidate(BRIMSTONE_VEIL_RAW)
        return orig_call(action, **kwargs)

    sandbox_engine.call = call_with_supersede

    delta = session.measure("Helmet", KRAKEN_DOME_RAW, candidate_id)

    assert delta is None
    assert session.is_healthy is True
    assert session.unhealthy_reason is None

    import_calls = [kw["xml"] for action, kw in sandbox_engine.calls if action == "import_build"]
    assert len(import_calls) >= 2
    assert import_calls[-1] == session.xml


def test_measure_engine_error_marks_unhealthy():
    """EngineError on equip_item marks session unhealthy with 'Engine error: ...' and restores baseline."""
    session, _main_engine, sandbox_engine = _create_session()
    candidate_id = session.submit_candidate(KRAKEN_DOME_RAW)
    sandbox_engine.calls.clear()

    orig_call = sandbox_engine.call

    def call_with_engine_error(action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "equip_item":
            raise EngineError("PoB process crashed on equip")
        return orig_call(action, **kwargs)

    sandbox_engine.call = call_with_engine_error

    delta = session.measure("Helmet", KRAKEN_DOME_RAW, candidate_id)

    assert delta is None
    assert session.is_healthy is False
    assert session.unhealthy_reason is not None
    assert session.unhealthy_reason.startswith("Engine error:")
    assert "PoB process crashed on equip" in session.unhealthy_reason

    import_calls = [kw["xml"] for action, kw in sandbox_engine.calls if action == "import_build"]
    assert len(import_calls) >= 2
    assert import_calls[-1] == session.xml


def test_measure_recovers_unhealthy_session():
    """An unhealthy session triggers auto-recovery during measure, returning delta and restoring health."""
    session, _main_engine, sandbox_engine = _create_session()

    session.is_healthy = False
    session.unhealthy_reason = "Engine error: prior crash"

    candidate_id = session.submit_candidate(KRAKEN_DOME_RAW)
    sandbox_engine.calls.clear()

    delta = session.measure("Helmet", KRAKEN_DOME_RAW, candidate_id)

    assert delta is not None
    assert session.is_healthy is True
    assert session.unhealthy_reason is None
    assert delta.slot == "Helmet"

    actions = [action for action, _kw in sandbox_engine.calls]
    assert "restart" in actions
    assert "equip_item" in actions


def test_measure_restore_failure_degrades_health(caplog: pytest.LogCaptureFixture):
    """When baseline restore raises in finally, measure logs a warning and degrades session health."""
    session, _main_engine, sandbox_engine = _create_session()
    candidate_id = session.submit_candidate(KRAKEN_DOME_RAW)

    orig_call = sandbox_engine.call
    restore_attempted = False

    def call_failing_restore(action: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal restore_attempted
        if action == "import_build" and any(a == "equip_item" for a, _ in sandbox_engine.calls):
            restore_attempted = True
            sandbox_engine.calls.append((action, kwargs))
            raise EngineError("Simulated baseline restore failure")
        return orig_call(action, **kwargs)

    sandbox_engine.call = call_failing_restore

    with caplog.at_level(logging.WARNING):
        delta = session.measure("Helmet", KRAKEN_DOME_RAW, candidate_id)

    assert restore_attempted is True
    assert session.is_healthy is False
    assert session.unhealthy_reason is not None
    assert session.unhealthy_reason.startswith("Baseline restore failed:")
    assert "Simulated baseline restore failure" in session.unhealthy_reason
    assert any("Failed to restore baseline in PoB2 sandbox" in rec.message for rec in caplog.records)
    assert delta is not None


def test_measure_never_touches_main_engine():
    """During measure, only the sandbox engine receives calls; main engine receives none."""
    session, main_engine, sandbox_engine = _create_session()

    main_engine.calls.clear()
    main_engine.call_log.clear()
    sandbox_engine.calls.clear()
    sandbox_engine.call_log.clear()

    candidate_id = session.submit_candidate(KRAKEN_DOME_RAW)
    delta = session.measure("Helmet", KRAKEN_DOME_RAW, candidate_id)

    assert delta is not None
    assert len(main_engine.calls) == 0
    assert len(main_engine.call_log) == 0

    sandbox_actions = [action for action, _kw in sandbox_engine.calls]
    assert "import_build" in sandbox_actions
    assert "equip_item" in sandbox_actions
    assert "calc_stats" in sandbox_actions
    assert "get_defenses" in sandbox_actions

