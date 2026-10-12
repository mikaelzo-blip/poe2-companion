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
            return {
                "mainSocketGroup": 1,
                "groups": [
                    {"index": 1, "enabled": True, "activeSkill": "Virtuous Barrier", "gems": []},
                    {"index": 2, "enabled": True, "activeSkill": "Flameblast", "gems": []},
                    {"index": 3, "enabled": True, "activeSkill": "Oil Grenade", "gems": []},
                    {"index": 4, "enabled": False, "activeSkill": "Big Nuke", "gems": []},
                ],
            }
        elif action == "set_main_skill":
            # only Flameblast (group 2) uses the equipped weapon
            dps = {1: 0.0, 2: 50.0, 3: 80.0, 4: 999.0}[kw["group"]]
            return {"mainDPS": dps + (25.0 if self._equipped and kw["group"] == 2 else 0.0)}
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
    """Groups locked right before each stat reading (probe calls excluded)."""
    calls = s.sandbox_engine.calls
    return [kw["group"] for (a, kw), (nxt, _) in zip(calls, calls[1:]) if a == "set_main_skill" and nxt == "get_defenses"]


def test_main_group_set_on_initialize(session):
    assert session.main_group == 3
    assert session.get_primary_socket_group() == 3


def test_measure_swap_slot_activates_set2_and_locks_skill(session):
    d = session.measure("Weapon 1 Swap", CROSSBOW, session.submit_candidate(CROSSBOW))
    imports = _imports(session)
    assert 'useSecondWeaponSet="true"' in imports[0]
    assert _locks(session) == [2, 2]  # the group the crossbow changes, not the highest-DPS one
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


def test_initialize_picks_highest_dps_group(session):
    assert session.main_group == 3
    set_skill_indices = [
        (i, kw["group"])
        for i, (a, kw) in enumerate(session.engine.calls)
        if a == "set_main_skill"
    ]
    assert set_skill_indices
    last_set_idx, last_group = set_skill_indices[-1]
    assert last_group == 3
    calc_stats_indices = [
        i for i, (a, kw) in enumerate(session.engine.calls)
        if a == "calc_stats" and i > last_set_idx
    ]
    assert len(calc_stats_indices) > 0


def test_measure_locks_guide_main_skill(session):
    session.measure("Gloves", GLOVES, session.submit_candidate(GLOVES), main_skill="Flameblast")
    assert _locks(session) == [2, 2]


def test_measure_unmatched_main_skill_falls_back(session):
    session.measure("Gloves", GLOVES, session.submit_candidate(GLOVES), main_skill="Nonexistent Skill")
    assert _locks(session) == [3, 3]


def test_weapon_slot_overrides_guide_skill_with_most_changed_group(session):
    session.measure("Weapon 1 Swap", CROSSBOW, session.submit_candidate(CROSSBOW), main_skill="Oil Grenade")
    assert _locks(session) == [2, 2]


def test_weapon_slot_keeps_guide_skill_when_no_group_changes(session):
    session.skill_groups = [1, 3]  # neither group reacts to the weapon
    session.measure("Weapon 1 Swap", CROSSBOW, session.submit_candidate(CROSSBOW), main_skill="Oil Grenade")
    assert _locks(session) == [3, 3]


def test_find_socket_group_crossbow_alias_without_match_returns_none(session):
    assert session.find_socket_group_for_skill("CROSSBOW_LEVELING") is None

