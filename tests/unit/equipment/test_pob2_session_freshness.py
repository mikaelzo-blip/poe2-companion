import json

import pytest
from unittest.mock import MagicMock

from companion import dashboard_server
from companion.dashboard_api import _build_eval_context
from companion.equipment.pob2_equipment_advisor import Pob2EquipmentSession

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


@pytest.fixture(autouse=True)
def _clean_refreshing(monkeypatch):
    monkeypatch.setattr(dashboard_server, "_REFRESHING", set())


def test_needs_refresh_on_level_up_zone_change_and_age():
    s = Pob2EquipmentSession("X"); s.level = 37; s.last_synced_at = 1000.0
    assert s.needs_refresh(37, "G2_1", now=1001.0) is False      # first zone observation
    assert s.needs_refresh(38, "G2_1", now=1001.0) is True
    assert s.needs_refresh(37, "G2_2", now=1001.0) is True
    assert s.needs_refresh(37, "G2_2", now=1000.0 + 601) is True


def test_maybe_refresh_runs_one_sync_at_a_time(monkeypatch):
    sess = MagicMock(); sess.needs_refresh.return_value = True
    monkeypatch.setitem(dashboard_server._GLOBAL_POB_SESSIONS, "X", sess)
    pending = []
    assert dashboard_server.maybe_refresh_pob_session("X", 40, None, spawn=pending.append) is True
    assert dashboard_server.maybe_refresh_pob_session("X", 40, None, spawn=pending.append) is False
    pending[0]()                                            # run the queued refresh
    sess.sync_character.assert_called_once()
    assert dashboard_server.maybe_refresh_pob_session("X", 40, None, spawn=pending.append) is True


def test_refresh_sync_failure_keeps_session(monkeypatch):
    sess = MagicMock(); sess.needs_refresh.return_value = True; sess.sync_character.return_value = False
    monkeypatch.setitem(dashboard_server._GLOBAL_POB_SESSIONS, "X", sess)
    dashboard_server.maybe_refresh_pob_session("X", 40, None, spawn=lambda fn: fn())
    sess.close.assert_not_called()
    assert dashboard_server._GLOBAL_POB_SESSIONS["X"] is sess


def test_effective_level_prefers_newer_character_file(tmp_path):
    (tmp_path / "characters").mkdir()
    (tmp_path / "characters" / "X.json").write_text(json.dumps({"level": {"value": 53}}))
    ctx = _build_eval_context({"character_id": "X", "stage": "auto"}, SAMPLE_BOOTS_TEXT, tmp_path, MagicMock(level=37))
    assert ctx.char_level == 53


def _real_session(level=37):
    s = Pob2EquipmentSession("X"); s.level = level; s.last_synced_at = 1000.0
    s.sync_character = MagicMock(return_value=False)
    return s


def test_failed_sync_is_rate_limited_to_60s(monkeypatch):
    monkeypatch.setitem(dashboard_server._GLOBAL_POB_SESSIONS, "X", _real_session())
    run = lambda fn: fn()
    assert dashboard_server.maybe_refresh_pob_session("X", 40, None, spawn=run, now=1001.0) is True
    assert dashboard_server.maybe_refresh_pob_session("X", 41, None, spawn=run, now=1002.0) is False
    assert dashboard_server.maybe_refresh_pob_session("X", 41, None, spawn=run, now=1062.0) is True


def test_zone_change_during_inflight_refresh_still_triggers(monkeypatch):
    monkeypatch.setitem(dashboard_server._GLOBAL_POB_SESSIONS, "X", _real_session())
    pending = []
    mr = dashboard_server.maybe_refresh_pob_session
    assert mr("X", 37, "A", spawn=pending.append, now=1001.0) is False   # first zone observation
    assert mr("X", 37, "B", spawn=pending.append, now=1002.0) is True
    assert mr("X", 37, "C", spawn=pending.append, now=1003.0) is False   # in flight
    pending[0]()
    assert mr("X", 37, "C", spawn=pending.append, now=1070.0) is True


def test_ggg_level_lag_does_not_retrigger(monkeypatch):
    monkeypatch.setitem(dashboard_server._GLOBAL_POB_SESSIONS, "X", _real_session())
    run = lambda fn: fn()
    mr = dashboard_server.maybe_refresh_pob_session
    assert mr("X", 40, None, spawn=run, now=1001.0) is True   # sync leaves session level at 37
    assert mr("X", 40, None, spawn=run, now=1010.0) is False
    assert mr("X", 40, None, spawn=run, now=1100.0) is False
    assert mr("X", 41, None, spawn=run, now=1101.0) is True


def test_no_level_trigger_when_session_level_unknown():
    s = Pob2EquipmentSession("X"); s.last_synced_at = 1000.0
    assert s.needs_refresh(40, None, now=1001.0) is False


@pytest.mark.parametrize("synced", [True, False])
def test_refresh_applies_session_to_runtime_only_after_successful_sync(monkeypatch, synced):
    sess = MagicMock(); sess.needs_refresh.return_value = True
    sess.sync_character.return_value = synced
    monkeypatch.setitem(dashboard_server._GLOBAL_POB_SESSIONS, "X", sess)
    applied = []
    monkeypatch.setattr(dashboard_server, "_apply_session", lambda cid, s: applied.append(cid))
    pending = []
    dashboard_server.maybe_refresh_pob_session("X", 40, None, spawn=pending.append)
    pending[0]()
    assert applied == (["X"] if synced else [])


def test_get_or_create_applies_session_after_successful_init(monkeypatch):
    import companion.equipment.pob2_equipment_advisor as adv
    fake = MagicMock(); fake.initialize.return_value = True
    fake.character_name = "ZED"; fake.is_available = True
    monkeypatch.setattr(adv, "Pob2EquipmentSession", lambda character_name: fake)
    monkeypatch.setattr(dashboard_server, "normalize_char_id", lambda c: c)
    monkeypatch.setattr(dashboard_server, "_GLOBAL_POB_SESSIONS", {})
    applied = []
    monkeypatch.setattr(dashboard_server, "_apply_session", lambda cid, s: applied.append((cid, s)))
    assert dashboard_server.get_or_create_pob_session("ZED", force_retry=True) is fake
    assert applied == [("ZED", fake)]


def test_concurrent_get_or_create_creates_one_session_and_no_orphans(monkeypatch):
    import threading
    import time
    import companion.equipment.pob2_equipment_advisor as adv

    created = []

    class SlowSession:
        def __init__(self, character_name):
            self.character_name, self.is_available, self.closed = character_name, False, False
            created.append(self)

        def initialize(self):
            time.sleep(0.3)  # a real init takes seconds (GGG fetch + docker run)
            self.is_available = True
            return True

        def close(self):
            self.closed = True

    monkeypatch.setattr(adv, "Pob2EquipmentSession", SlowSession)
    monkeypatch.setattr(dashboard_server, "normalize_char_id", lambda c: c)
    monkeypatch.setattr(dashboard_server, "_GLOBAL_POB_SESSIONS", {})
    monkeypatch.setattr(dashboard_server, "_FAILED_CHARACTERS", {})
    monkeypatch.setattr(dashboard_server, "_apply_session", lambda cid, s: None)
    results = []
    threads = [threading.Thread(target=lambda: results.append(
        dashboard_server.get_or_create_pob_session("ZED", force_retry=True))) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert len(created) == 1 and not created[0].closed
    assert results == [created[0]] * 4
