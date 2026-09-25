"""Unit tests for Pob2EquipmentSession weapon simulation and ambiguous 1H dual-placement.

Enforces:
- Mathematical execution only: mutates PoB build atomically, calculates deltas,
  and restores complete baseline in finally.
- Strict absence of EQUIP/REJECT verdict inside the generic session.
- Regression G: Ambiguous 1H placement dual-simulates within the SAME target set
  against the exact same baseline with no arbitrary weighted winner.
- Same-baseline invariant across simulation steps and error cases.
"""

import threading
import pytest
from companion.equipment.parser import parse_item_text
from companion.equipment.pob2_equipment_advisor import (
    DualWeaponSimulationResult,
    Pob2EquipmentSession,
    PobEquipmentDelta,
)
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.equipment.weapon_topology import (
    WeaponArchetype,
    WeaponTopologyPlan,
    WeaponTopologyResolver,
)
from companion.equipment.fubgun_weapon_router import (
    FubgunWeaponProfileRouter,
    WeaponSimulationContext,
)
from tests.unit.equipment.test_pob2_helmet_advisor import FakePobEngine, FakePoeApi

STAFF_TEXT = """Item Class: Two Hand Staves
Rarity: Rare
Volcano Pillar
Chiming Staff
--------
Physical Damage: 45-93
--------
Requirements:
Level: 52
--------
+20% to Fire Resistance
+2 to Level of all Fire Spell Skill Gems
"""

CROSSBOW_TEXT = """Item Class: Crossbows
Rarity: Rare
Gloom Piercer
Bombard Crossbow
--------
Physical Damage: 30-75
--------
Requirements:
Level: 52
--------
+15% to Attack Speed
"""

WAND_TEXT = """Item Class: Wands
Rarity: Rare
Spire Wand
Opal Wand
--------
Requirements:
Level: 45
--------
+15% to Lightning Resistance
"""


def test_simulate_weapon_plan_mathematical_only():
    """simulate_weapon_plan calculates deltas without deciding EQUIP/REJECT."""
    fake_engine = FakePobEngine()
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True

    staff = parse_item_text(STAFF_TEXT)
    resolver = WeaponTopologyResolver()
    plan = resolver.resolve_topology(staff, target_set=WeaponSetContext.WEAPON_SET_1)

    cid = session.submit_candidate(STAFF_TEXT, candidate_name="Volcano Pillar", slot="Weapon 1")
    context = WeaponSimulationContext(
        target_set=WeaponSetContext.WEAPON_SET_1,
        target_slot="Weapon 1",
        skill_context="Flameblast",
        weapon_archetype=WeaponArchetype.TWO_HAND_STAFF,
        topology_plan=plan,
        build_stage=BuildProgressionStage.SWAP_52,
        candidate_id=cid,
        candidate_name="Volcano Pillar",
        raw_candidate=STAFF_TEXT,
    )

    delta = session.simulate_weapon_plan(context)
    assert delta is not None
    assert isinstance(delta, PobEquipmentDelta)
    assert delta.slot == "Weapon 1"
    # Mathematical properties only: no verdict or equip/reject decision on the delta model
    assert not hasattr(delta, "verdict")
    assert not hasattr(delta, "verdict_code")

    # Verified baseline restored in engine
    assert fake_engine.call_log[-1] == "import_build"


def test_simulate_weapon_plan_failure_restores_baseline():
    """Engine exception during weapon simulation restores baseline in finally block."""
    class FailingPobEngine(FakePobEngine):
        def call(self, method: str, **kwargs):
            if method == "equip_item":
                raise RuntimeError("Simulated weapon crash")
            return super().call(method, **kwargs)

    failing_engine = FailingPobEngine()
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: failing_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True

    staff = parse_item_text(STAFF_TEXT)
    resolver = WeaponTopologyResolver()
    plan = resolver.resolve_topology(staff, target_set=WeaponSetContext.WEAPON_SET_1)

    cid = session.submit_candidate(STAFF_TEXT, candidate_name="Volcano Pillar", slot="Weapon 1")
    context = WeaponSimulationContext(
        target_set=WeaponSetContext.WEAPON_SET_1,
        target_slot="Weapon 1",
        skill_context="Flameblast",
        weapon_archetype=WeaponArchetype.TWO_HAND_STAFF,
        topology_plan=plan,
        build_stage=BuildProgressionStage.SWAP_52,
        candidate_id=cid,
        candidate_name="Volcano Pillar",
        raw_candidate=STAFF_TEXT,
    )

    delta = session.simulate_weapon_plan(context)
    assert delta is None
    # Baseline was restored in finally block
    assert failing_engine.call_log[-1] == "import_build"


def test_regression_g_ambiguous_one_hand_dual_placement_same_baseline():
    """Regression G: Ambiguous 1H placement dual-simulates within SAME set with same baseline invariant."""
    fake_engine = FakePobEngine()
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True

    wand = parse_item_text(WAND_TEXT)
    cid = session.submit_candidate(WAND_TEXT, candidate_name="Spire Wand", slot="Weapon 1")

    # Ambiguous placement in Set 1: Weapon 1 vs Weapon 2
    dual_result = session.simulate_ambiguous_1h_weapon(
        raw_candidate=WAND_TEXT,
        candidate_id=cid,
        candidate_name="Spire Wand",
        target_set=WeaponSetContext.WEAPON_SET_1,
        build_stage=BuildProgressionStage.LEVELING_15_32,
    )

    assert dual_result is not None
    assert isinstance(dual_result, DualWeaponSimulationResult)
    assert dual_result.slot1_delta is not None
    assert dual_result.slot2_delta is not None
    assert dual_result.slot1_delta.slot == "Weapon 1"
    assert dual_result.slot2_delta.slot == "Weapon 2"

    # Both simulations occurred against the hot engine baseline
    assert fake_engine.call_log.count("equip_item") == 2
    # Baseline was restored after slot 1 and after slot 2
    assert fake_engine.call_log[-1] == "import_build"


def test_ambiguous_1h_weapon_failure_restores_baseline():
    """Ambiguous 1H weapon simulation failure in slot 1 or 2 guarantees baseline restoration."""
    class FailingPobEngine(FakePobEngine):
        def call(self, method: str, **kwargs):
            if method == "equip_item" and kwargs.get("slot") == "Weapon 2":
                raise RuntimeError("Slot 2 simulation crashed")
            return super().call(method, **kwargs)

    failing_engine = FailingPobEngine()
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: failing_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True

    cid = session.submit_candidate(WAND_TEXT, candidate_name="Spire Wand", slot="Weapon 1")
    dual_result = session.simulate_ambiguous_1h_weapon(
        raw_candidate=WAND_TEXT,
        candidate_id=cid,
        candidate_name="Spire Wand",
        target_set=WeaponSetContext.WEAPON_SET_1,
        build_stage=BuildProgressionStage.LEVELING_15_32,
    )
    assert dual_result is not None
    assert dual_result.slot1_delta is not None
    assert dual_result.slot2_delta is None
    # Baseline was restored in finally block even after slot 2 crashed
    assert failing_engine.call_log[-1] == "import_build"


def test_simulate_weapon_plan_activates_weapon_set_and_skill_context():
    """simulate_weapon_plan activates Weapon Set 2 in XML and selects active skill context."""
    class TrackingEngine(FakePobEngine):
        def __init__(self):
            super().__init__()
            self.detailed_calls = []

        def call(self, action: str, **kwargs):
            self.detailed_calls.append((action, kwargs))
            if action == "list_skills":
                return {
                    "mainSocketGroup": 1,
                    "groups": [
                        {"index": 1, "activeSkill": "Flameblast", "gems": [{"name": "Flameblast"}]},
                        {"index": 2, "activeSkill": "Oil Grenade", "gems": [{"name": "Oil Grenade"}]},
                    ],
                }
            if action == "set_main_skill":
                return {"activeSkill": "Oil Grenade", "mainSocketGroup": kwargs.get("group")}
            return super().call(action, **kwargs)

    tracking_engine = TrackingEngine()
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: tracking_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True

    xbow = parse_item_text(CROSSBOW_TEXT)
    resolver = WeaponTopologyResolver()
    plan = resolver.resolve_topology(xbow, target_set=WeaponSetContext.WEAPON_SET_2)

    cid = session.submit_candidate(CROSSBOW_TEXT, candidate_name="Gloom Piercer", slot="Weapon 1 Swap")
    context = WeaponSimulationContext(
        target_set=WeaponSetContext.WEAPON_SET_2,
        target_slot="Weapon 1 Swap",
        skill_context="Oil Grenade",
        weapon_archetype=WeaponArchetype.TWO_HAND_CROSSBOW,
        topology_plan=plan,
        build_stage=BuildProgressionStage.SWAP_52,
        candidate_id=cid,
        candidate_name="Gloom Piercer",
        raw_candidate=CROSSBOW_TEXT,
    )

    delta = session.simulate_weapon_plan(context)
    assert delta is not None
    assert delta.slot == "Weapon 1 Swap"

    # Verify set_main_skill was called for Oil Grenade (group 2)
    set_skill_calls = [args for action, args in tracking_engine.detailed_calls if action == "set_main_skill"]
    assert len(set_skill_calls) >= 1
    assert set_skill_calls[0].get("group") == 2

    # Verify import_build before equip activated useSecondWeaponSet="true"
    import_calls = [args.get("xml", "") for action, args in tracking_engine.detailed_calls if action == "import_build"]
    assert any('useSecondWeaponSet="true"' in x or "useSecondWeaponSet='true'" in x for x in import_calls[:-1])
    # Verify final call restored original baseline
    assert tracking_engine.call_log[-1] == "import_build"


def test_simulate_weapon_plan_stale_suppression_skips_simulation():
    """When newer candidate B arrives, candidate A is stale and skips expensive simulation."""
    fake_engine = FakePobEngine()
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True

    xbow = parse_item_text(CROSSBOW_TEXT)
    resolver = WeaponTopologyResolver()
    plan = resolver.resolve_topology(xbow, target_set=WeaponSetContext.WEAPON_SET_1)

    # 1. Candidate A submitted
    id_a = session.submit_candidate(CROSSBOW_TEXT, candidate_name="Candidate A", slot="Weapon 1")
    assert id_a == 1

    # 2. Candidate B submitted before A simulates (coalescing burst)
    id_b = session.submit_candidate(CROSSBOW_TEXT, candidate_name="Candidate B", slot="Weapon 1")
    assert id_b == 2

    # 3. Candidate A attempts simulation
    context_a = WeaponSimulationContext(
        target_set=WeaponSetContext.WEAPON_SET_1,
        target_slot="Weapon 1",
        skill_context="CROSSBOW_LEVELING",
        weapon_archetype=WeaponArchetype.TWO_HAND_CROSSBOW,
        topology_plan=plan,
        build_stage=BuildProgressionStage.LEVELING_15_32,
        candidate_id=id_a,
        candidate_name="Candidate A",
        raw_candidate=CROSSBOW_TEXT,
    )
    calls_before = len(fake_engine.call_log)
    delta_a = session.simulate_weapon_plan(context_a)
    # Stale candidate A skipped before acquiring simulation!
    assert delta_a is None
    assert len(fake_engine.call_log) == calls_before

    # 4. Candidate B simulates successfully
    context_b = WeaponSimulationContext(
        target_set=WeaponSetContext.WEAPON_SET_1,
        target_slot="Weapon 1",
        skill_context="CROSSBOW_LEVELING",
        weapon_archetype=WeaponArchetype.TWO_HAND_CROSSBOW,
        topology_plan=plan,
        build_stage=BuildProgressionStage.LEVELING_15_32,
        candidate_id=id_b,
        candidate_name="Candidate B",
        raw_candidate=CROSSBOW_TEXT,
    )
    delta_b = session.simulate_weapon_plan(context_b)
    assert delta_b is not None
    assert delta_b.candidate_id == 2
    assert "equip_item" in fake_engine.call_log


def test_simulate_weapon_plan_in_flight_staleness_restores_and_discards():
    """If candidate B arrives while candidate A is actively inside the simulation lock,
    candidate A completes calculations, checks staleness, restores baseline, and returns None.
    """
    active = False

    class InFlightStaleEngine(FakePobEngine):
        def __init__(self, on_calc_hook):
            super().__init__()
            self.on_calc_hook = on_calc_hook

        def call(self, action: str, **kwargs):
            if action == "calc_stats" and active:
                self.on_calc_hook()
            return super().call(action, **kwargs)

    def trigger_b_arrival():
        session.submit_candidate(CROSSBOW_TEXT, candidate_name="Candidate B", slot="Weapon 1")

    engine = InFlightStaleEngine(on_calc_hook=trigger_b_arrival)
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True

    xbow = parse_item_text(CROSSBOW_TEXT)
    resolver = WeaponTopologyResolver()
    plan = resolver.resolve_topology(xbow, target_set=WeaponSetContext.WEAPON_SET_1)

    active = True
    id_a = session.submit_candidate(CROSSBOW_TEXT, candidate_name="Candidate A", slot="Weapon 1")
    assert id_a == 1

    context_a = WeaponSimulationContext(
        target_set=WeaponSetContext.WEAPON_SET_1,
        target_slot="Weapon 1",
        skill_context="CROSSBOW_LEVELING",
        weapon_archetype=WeaponArchetype.TWO_HAND_CROSSBOW,
        topology_plan=plan,
        build_stage=BuildProgressionStage.LEVELING_15_32,
        candidate_id=id_a,
        candidate_name="Candidate A",
        raw_candidate=CROSSBOW_TEXT,
    )

    delta_a = session.simulate_weapon_plan(context_a)
    # Stale candidate A was invalidated mid-flight and returned None
    assert delta_a is None
    # Baseline was safely restored in finally
    assert engine.call_log[-1] == "import_build"
