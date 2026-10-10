import json
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
