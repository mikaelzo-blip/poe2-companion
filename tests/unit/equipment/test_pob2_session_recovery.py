from pathlib import Path
from typing import Any

from companion.dashboard_api import get_dashboard_status
from companion.equipment.pob2_equipment_advisor import (
    EngineError,
    Pob2EquipmentSession,
)


class FakePobEngine:
    def __init__(self):
        self.call_log: list[str] = []

    def call(self, action: str, **kwargs: Any) -> dict[str, Any]:
        self.call_log.append(action)
        if action == "import_character":
            return {
                "className": "Mercenary",
                "level": 17,
                "xml": "<PathOfBuilding><Build/></PathOfBuilding>",
            }
        elif action == "get_equipped":
            return {"equipped": True, "name": "Brimstone Veil", "raw": ""}
        return {"success": True}


class FakePoeApi:
    def fetch_character_raw(self, character_name: str) -> str:
        return f'{{"character": "{character_name}"}}'


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
