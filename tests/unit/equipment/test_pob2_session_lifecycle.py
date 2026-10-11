from unittest.mock import MagicMock

from companion import dashboard_server
from companion.equipment.pob2_equipment_advisor import Pob2EquipmentSession


class CountingEngine:
    def __init__(self, fail_on=None):
        self.closed = 0
        self.fail_on = fail_on

    def call(self, cmd, **kw):
        if cmd == self.fail_on:
            raise RuntimeError("boom")
        return {"xml": "<x/>", "className": "Mercenary", "level": 30} if cmd == "import_character" else {}

    def close(self):
        self.closed += 1


def test_initialize_failure_closes_both_engines():
    engines = []

    def factory():
        e = CountingEngine(fail_on="import_character")
        engines.append(e)
        return e

    sess = Pob2EquipmentSession("X", engine_factory=factory, poe_api_client=MagicMock())
    assert sess.initialize() is False
    assert [e.closed for e in engines] == [1, 1]
    assert "boom" in sess.unavailable_reason


def test_invalidate_syncs_and_keeps_session(monkeypatch):
    sess = MagicMock()
    sess.sync_character.return_value = False
    monkeypatch.setitem(dashboard_server._GLOBAL_POB_SESSIONS, "X", sess)
    dashboard_server.invalidate_pob_session("X")
    sess.sync_character.assert_called_once()
    sess.close.assert_not_called()
    assert dashboard_server._GLOBAL_POB_SESSIONS["X"] is sess


def test_invalidate_all_closes_every_session(monkeypatch):
    a, b = MagicMock(), MagicMock()
    monkeypatch.setattr(dashboard_server, "_GLOBAL_POB_SESSIONS", {"A": a, "B": b})
    dashboard_server.invalidate_pob_session()
    a.close.assert_called_once()
    b.close.assert_called_once()
    assert dashboard_server._GLOBAL_POB_SESSIONS == {}


def test_get_or_create_closes_unavailable_cached_session(monkeypatch):
    stale = MagicMock(is_available=False, character_name="X")
    monkeypatch.setattr(dashboard_server, "_GLOBAL_POB_SESSIONS", {"X": stale})
    monkeypatch.setattr(dashboard_server, "_FAILED_CHARACTERS", {})
    fresh = MagicMock()
    fresh.initialize.return_value = False
    monkeypatch.setattr("companion.equipment.pob2_equipment_advisor.Pob2EquipmentSession", lambda **kw: fresh)
    monkeypatch.setattr(dashboard_server, "normalize_char_id", lambda c: c)
    assert dashboard_server.get_or_create_pob_session("X", force_retry=True) is None
    stale.close.assert_called_once()
    assert "X" not in dashboard_server._GLOBAL_POB_SESSIONS
