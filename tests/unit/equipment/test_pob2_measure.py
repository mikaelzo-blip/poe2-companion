"""Tests for Pob2EquipmentSession.measure(): weapon-set toggle, skill lock, clear_slots, per-source staleness."""
from __future__ import annotations

from typing import Any

import pytest

from companion.equipment.pob2_equipment_advisor import Pob2EquipmentSession

CROSSBOW = "Rarity: Rare\nCrossbow Thing\nAdd Crossbow"
STAFF = "Rarity: Rare\nStaff Thing\nAdd Staff"
GLOVES = "Rarity: Rare\nGlove Thing\nAdd Gloves"
RING = "Rarity: Rare\nRing Thing\nAdd Ring"

FAKE_FIRE_BEFORE = -35
FAKE_FIRE_AFTER = 5
BASE_XML = (
    '<PathOfBuilding><Items><ItemSet id="1">'
    '<Slot name="Weapon 2" itemId="5"/>'
    "</ItemSet></Items></PathOfBuilding>"
)


class FakeEngine:
    """Records every call; stats flip to the "after" values once an item is equipped."""

    def __init__(self, fail_equip: bool = False):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_equip = fail_equip
        self._equipped = False

    def call(self, action: str, **kw: Any) -> dict[str, Any]:
        self.calls.append((action, kw))
        if action == "import_character":
            return {"className": "Mercenary", "level": 30, "xml": BASE_XML}
        if action == "import_build":
            self._equipped = False
        elif action == "equip_item":
            if self.fail_equip:
                raise RuntimeError("boom")
            self._equipped = True
        elif action == "list_skills":
            return {"mainSocketGroup": 3, "groups": []}
        elif action == "get_defenses":
            return {"Life": 100, "Armour": 0, "Evasion": 0, "EnergyShield": 0,
                    "TotalEHP": 120.0 if self._equipped else 100.0}
        elif action == "calc_stats":
            return {
                "defense": {
                    "FireResist": FAKE_FIRE_AFTER if self._equipped else FAKE_FIRE_BEFORE,
                    "ColdResist": 0, "LightningResist": 0, "ChaosResist": -60,
                },
                "offense": {"CombinedDPS": 200.0 if self._equipped else 100.0},
            }
        return {}


class FakeApi:
    def fetch_character_raw(self, name: str) -> str:
        return "{}"


def _make(fail_equip: bool = False) -> Pob2EquipmentSession:
    engines = iter([FakeEngine(), FakeEngine(fail_equip=fail_equip)])
    s = Pob2EquipmentSession(engine_factory=lambda: next(engines), poe_api_client=FakeApi())
    assert s.initialize()
    return s


@pytest.fixture
def session() -> Pob2EquipmentSession:
    return _make()


@pytest.fixture
def session_failing_equip() -> Pob2EquipmentSession:
    return _make(fail_equip=True)


def _imports(s: Pob2EquipmentSession) -> list[str]:
    return [kw["xml"] for a, kw in s.sandbox_engine.calls if a == "import_build"]


def _locks(s: Pob2EquipmentSession) -> list[int]:
    return [kw["group"] for a, kw in s.sandbox_engine.calls if a == "set_main_skill"]


def test_main_group_set_on_initialize(session):
    assert session.main_group == 3
    assert session.get_primary_socket_group() == 3


def test_measure_swap_slot_activates_set2_and_locks_skill(session):
    d = session.measure("Weapon 1 Swap", CROSSBOW, session.submit_candidate(CROSSBOW))
    imports = _imports(session)
    assert 'useSecondWeaponSet="true"' in imports[0]
    assert _locks(session) == [3, 3]
    assert imports[-1] == session.xml
    assert d.dps_after > d.dps_before and d.res_before["fire"] == FAKE_FIRE_BEFORE
    assert d.res_after["fire"] == FAKE_FIRE_AFTER and d.res_after["chaos"] == -60


def test_non_swap_slot_uses_set1(session):
    session.measure("Gloves", GLOVES, session.submit_candidate(GLOVES))
    assert 'useSecondWeaponSet="false"' in _imports(session)[0]


def test_clear_slots_only_affect_after(session):
    session.measure("Weapon 1", STAFF, session.submit_candidate(STAFF), clear_slots=("Weapon 2",))
    imports = _imports(session)
    assert 'name="Weapon 2" itemId="0"' not in imports[0] and 'itemId="0"' in imports[1]


def test_staleness_is_per_source(session):
    manual = session.submit_candidate("a", source="manual")
    session.submit_candidate("b", source="auto")
    assert not session.is_stale(manual, "manual")
    newer = session.submit_candidate("c", source="manual")
    assert session.is_stale(manual, "manual") and not session.is_stale(newer, "manual")


def test_stale_candidate_returns_none_and_skips_engine(session):
    old = session.submit_candidate(GLOVES)
    session.submit_candidate(GLOVES)
    assert session.measure("Gloves", GLOVES, old) is None
    assert session.sandbox_engine.calls == []


def test_restore_runs_when_equip_fails(session_failing_equip):
    assert session_failing_equip.measure("Gloves", GLOVES, 1) is None
    assert session_failing_equip.sandbox_engine.calls[-1][0] == "import_build"

