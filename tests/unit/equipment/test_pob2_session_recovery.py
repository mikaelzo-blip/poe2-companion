import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from companion.dashboard_api import get_dashboard_status
from companion.equipment.pob2_equipment_advisor import (
    EngineError,
    Pob2EquipmentSession,
)
from tests.unit.equipment.test_pob2_helmet_advisor import BRIMSTONE_VEIL_RAW, FakePobEngine, FakePoeApi

KRAKEN_DOME_RAW = (
    "Item Class: Helmets\n"
    "Rarity: Rare\n"
    "Kraken Dome\n"
    "Advanced Hunter Hood\n"
    "Evasion Rating: 150\n"
    "+45 to maximum Life\n"
    "+25% to Fire Resistance\n"
)


class RecoverableFailingEngine(FakePobEngine):
    def __init__(self):
        super().__init__()
        self.fail_engine_error = False
        self.restart_called = False
        self.fail_restore = False

    def restart(self) -> None:
        self.restart_called = True
        self.call_log.append("restart")

    def call(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "calc_stats" and self.fail_engine_error:
            self.fail_engine_error = False
            raise EngineError("Simulated engine IPC crash")
        if action == "import_build" and self.fail_restore:
            self.fail_restore = False
            raise EngineError("Simulated baseline restore failure")
        return super().call(action, **kwargs)


def test_session_health_initial_state():
    fake_engine = RecoverableFailingEngine()
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.is_healthy is True
    assert session.unhealthy_reason is None
    assert session.initialize() is True
    assert session.is_healthy is True


def test_session_marks_unhealthy_on_engine_error_without_auto_retry():
    fake_engine = RecoverableFailingEngine()
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True
    fake_engine.fail_engine_error = True

    cid1 = session.submit_candidate(KRAKEN_DOME_RAW, candidate_name="Kraken Dome")
    res1 = session.simulate_item(
        slot="Helmet",
        raw_candidate=KRAKEN_DOME_RAW,
        candidate_id=cid1,
        candidate_name="Kraken Dome",
    )
    assert res1 is None
    assert session.is_healthy is False
    assert "Simulated engine IPC crash" in str(session.unhealthy_reason)
    # Ensure it did not auto-retry immediately in the same call
    assert fake_engine.restart_called is False


def test_session_auto_recovers_on_next_simulation_call():
    fake_engine = RecoverableFailingEngine()
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True
    fake_engine.fail_engine_error = True

    # 1. First call fails and marks unhealthy
    cid1 = session.submit_candidate(KRAKEN_DOME_RAW, candidate_name="Kraken Dome")
    assert session.simulate_item(
        slot="Helmet",
        raw_candidate=KRAKEN_DOME_RAW,
        candidate_id=cid1,
        candidate_name="Kraken Dome",
    ) is None
    assert session.is_healthy is False

    # 2. Next call attempts single restart + baseline restore, then simulates new candidate
    cid2 = session.submit_candidate(KRAKEN_DOME_RAW, candidate_name="Kraken Dome 2")
    res2 = session.simulate_item(
        slot="Helmet",
        raw_candidate=KRAKEN_DOME_RAW,
        candidate_id=cid2,
        candidate_name="Kraken Dome 2",
    )
    assert fake_engine.restart_called is True
    assert session.is_healthy is True
    assert session.unhealthy_reason is None
    assert res2 is not None
    assert res2.candidate_name == "Kraken Dome 2"


def test_session_finally_restore_failure_logs_warning_and_degrades_health(caplog):
    fake_engine = RecoverableFailingEngine()
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True

    # Configure restore to fail in finally block
    fake_engine.fail_restore = True
    cid = session.submit_candidate(KRAKEN_DOME_RAW, candidate_name="Kraken Dome")

    with caplog.at_level(logging.WARNING):
        res = session.simulate_item(
            slot="Helmet",
            raw_candidate=KRAKEN_DOME_RAW,
            candidate_id=cid,
            candidate_name="Kraken Dome",
        )

    assert session.is_healthy is False
    assert "restore" in str(session.unhealthy_reason).lower()
    # Check that warning log was emitted (not silently swallowed by `except Exception: pass`)
    assert any("restore" in rec.message.lower() for rec in caplog.records)


def test_api_status_exposes_engine_health(tmp_path: Path):
    fake_engine = RecoverableFailingEngine()
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True

    status_healthy = get_dashboard_status(runtime_dir=tmp_path, char_id="BOMSHAK", pob_session=session)
    assert "engine_status" in status_healthy
    assert status_healthy["engine_status"]["available"] is True
    assert status_healthy["engine_status"]["healthy"] is True
    assert status_healthy["engine_status"]["unhealthy_reason"] is None
    assert status_healthy["status"]["engine_healthy"] is True

    # Degrade health
    session.is_healthy = False
    session.unhealthy_reason = "Simulated crash"

    status_unhealthy = get_dashboard_status(runtime_dir=tmp_path, char_id="BOMSHAK", pob_session=session)
    assert status_unhealthy["engine_status"]["healthy"] is False
    assert status_unhealthy["engine_status"]["unhealthy_reason"] == "Simulated crash"
    assert status_unhealthy["status"]["engine_healthy"] is False
