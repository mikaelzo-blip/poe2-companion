"""Unit tests for generic PoB2 Equipment Advisor foundation (TDD RED stage).

Validates:
1. Canonical slot validation: normalize and validate equipment slots; fail closed on unknown slots.
2. Generic simulate_item(slot, raw_candidate) support on Pob2EquipmentSession.
3. Thread-safe bookkeeping: request ID allocation and stale checks use safe synchronization
   independent from the expensive PoB engine lock.
4. Backward compatibility: Pob2HelmetSession is a thin facade/subclass preserving helmet-specific API.
5. Async burst coalescing: A starts, B arrives, C arrives, A finishes (discarded), B is skipped
   before simulation starts, C simulates only.
"""

from __future__ import annotations

import math
from pathlib import Path
import threading
import time
from typing import Any
import pytest

from companion.equipment.pob2_equipment_advisor import (
    CANONICAL_EQUIPMENT_SLOTS,
    POB2_PRODUCTION_SLOTS,
    Pob2EquipmentSession,
    PobEquipmentDelta,
    _clear_slots_in_xml,
    normalize_and_validate_pob_slot,
)
from companion.equipment.precedence import Verdict
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.schema import SlotType
from companion.equipment.pob2_helmet_advisor import (
    Pob2HelmetSession,
    PobHelmetDelta,
)
from tests.unit.equipment.test_pob2_helmet_advisor import (
    BRIMSTONE_VEIL_RAW,
    KRAKEN_DOME_RAW,
    FakePobEngine,
    FakePoeApi,
)


POB2_PRODUCTION_CORE_SLOTS: set[str] = {
    "Helmet",
    "Body Armour",
    "Gloves",
    "Boots",
    "Belt",
    "Amulet",
}


def test_production_core_slots_allowlist_matches_approved_milestone():
    """Milestone allowlist specifies exactly the 6 core slots, excluding Rings and Weapons."""
    from companion.equipment.live_watcher import POB2_PRODUCTION_CORE_SLOTS as PROD_SLOTS

    assert PROD_SLOTS == {
        "Helmet",
        "Body Armour",
        "Gloves",
        "Boots",
        "Belt",
        "Amulet",
    }
    # Explicitly assert Rings and Weapons are NOT enabled
    assert "Ring 1" not in PROD_SLOTS
    assert "Ring 2" not in PROD_SLOTS
    assert "Weapon 1" not in PROD_SLOTS
    assert "Weapon 2" not in PROD_SLOTS


def test_generic_fubgun_equipment_policy_evaluates_all_core_slots():
    """evaluate_fubgun_equipment_policy handles Body Armour, Gloves, Boots, Belt, Amulet, and Helmet."""
    from companion.equipment.fubgun_priorities import (
        evaluate_fubgun_equipment_policy,
        FubgunEquipmentRecommendation,
    )

    # 1. Body Armour: high Armour + Life is strong upgrade
    ba_delta = PobEquipmentDelta(
        slot="Body Armour",
        candidate_id=1,
        candidate_name="Obsidian Plate",
        current_item_name="Plate Vest",
        life_delta=40,
        fire_res_delta=15,
        cold_res_delta=0,
        lightning_res_delta=0,
        chaos_res_delta=0,
        armour_delta=120,
        evasion_delta=0,
        es_delta=0,
        ehp_delta=45.0,
        dps_delta=0.0,
    )
    rec_ba = evaluate_fubgun_equipment_policy(ba_delta, stage=BuildProgressionStage.LEVELING_15_32)
    assert isinstance(rec_ba, FubgunEquipmentRecommendation)
    assert rec_ba.verdict == Verdict.EQUIP_NOW
    assert "Body Armour" in rec_ba.formatted_output
    assert "Obsidian Plate" in rec_ba.formatted_output
    assert "+40 Life" in rec_ba.formatted_output
    assert "+120 Armour" in rec_ba.formatted_output

    # 2. Boots: defensive upgrade without MS or with MS
    boots_delta = PobEquipmentDelta(
        slot="Boots",
        candidate_id=2,
        candidate_name="Beryl Stride",
        current_item_name="Rawhide Boots",
        life_delta=25,
        fire_res_delta=0,
        cold_res_delta=15,
        lightning_res_delta=0,
        chaos_res_delta=0,
        armour_delta=50,
        evasion_delta=0,
        es_delta=0,
        movement_speed_delta=10.0,
        ehp_delta=30.0,
        dps_delta=0.0,
    )
    rec_boots = evaluate_fubgun_equipment_policy(boots_delta, stage=BuildProgressionStage.LEVELING_15_32)
    assert isinstance(rec_boots, FubgunEquipmentRecommendation)
    assert rec_boots.verdict == Verdict.EQUIP_NOW
    assert "Boots" in rec_boots.formatted_output
    assert "+25 Life" in rec_boots.formatted_output
    assert "+15% Cold Res" in rec_boots.formatted_output

    boots_loss_delta = boots_delta.model_copy(update={"movement_speed_delta": -10})
    rec_boots_loss = evaluate_fubgun_equipment_policy(
        boots_loss_delta,
        stage=BuildProgressionStage.LEVELING_15_32,
    )
    assert rec_boots_loss.verdict != Verdict.EQUIP_NOW
    assert "-10% Movement Speed" in rec_boots_loss.formatted_output

    # 3. Gloves: Life + Resistances
    gloves_delta = PobEquipmentDelta(
        slot="Gloves",
        candidate_id=3,
        candidate_name="Bramble Mitts",
        current_item_name="Cloth Gloves",
        life_delta=30,
        fire_res_delta=20,
        cold_res_delta=0,
        lightning_res_delta=0,
        chaos_res_delta=0,
        armour_delta=30,
        evasion_delta=0,
        es_delta=0,
        ehp_delta=25.0,
        dps_delta=2.5,
    )
    rec_gloves = evaluate_fubgun_equipment_policy(gloves_delta, stage=BuildProgressionStage.LEVELING_15_32)
    assert isinstance(rec_gloves, FubgunEquipmentRecommendation)
    assert rec_gloves.verdict == Verdict.EQUIP_NOW
    assert "Gloves" in rec_gloves.formatted_output
    assert "+30 Life" in rec_gloves.formatted_output

    # 4. Belt: Life + Resistances
    belt_delta = PobEquipmentDelta(
        slot="Belt",
        candidate_id=4,
        candidate_name="Vigour Clasp",
        current_item_name="Chain Belt",
        life_delta=35,
        fire_res_delta=0,
        cold_res_delta=0,
        lightning_res_delta=18,
        chaos_res_delta=0,
        armour_delta=0,
        evasion_delta=0,
        es_delta=0,
        ehp_delta=35.0,
        dps_delta=0.0,
    )
    rec_belt = evaluate_fubgun_equipment_policy(belt_delta, stage=BuildProgressionStage.LEVELING_15_32)
    assert isinstance(rec_belt, FubgunEquipmentRecommendation)
    assert rec_belt.verdict == Verdict.EQUIP_NOW
    assert "Belt" in rec_belt.formatted_output
    assert "+35 Life" in rec_belt.formatted_output

    # 5. Amulet: Life + Resistances
    amulet_delta = PobEquipmentDelta(
        slot="Amulet",
        candidate_id=5,
        candidate_name="Torment Gorget",
        current_item_name="Coral Amulet",
        life_delta=20,
        fire_res_delta=12,
        cold_res_delta=12,
        lightning_res_delta=0,
        chaos_res_delta=0,
        armour_delta=0,
        evasion_delta=0,
        es_delta=0,
        ehp_delta=30.0,
        dps_delta=1.0,
    )
    rec_amulet = evaluate_fubgun_equipment_policy(amulet_delta, stage=BuildProgressionStage.LEVELING_15_32)
    assert isinstance(rec_amulet, FubgunEquipmentRecommendation)
    assert rec_amulet.verdict == Verdict.EQUIP_NOW
    assert "Amulet" in rec_amulet.formatted_output
    assert "+20 Life" in rec_amulet.formatted_output

    # 7. Core armor slot with resistance gain despite minor ES / EHP delta
    gloves_res_delta = PobEquipmentDelta(
        slot="Gloves",
        candidate_id=7,
        candidate_name="Rune Mitts",
        current_item_name="Silk Gloves",
        life_delta=0,
        fire_res_delta=14,
        cold_res_delta=0,
        lightning_res_delta=0,
        chaos_res_delta=0,
        armour_delta=30,
        evasion_delta=0,
        es_delta=-25,
        ehp_delta=-3.2,
        dps_delta=0.0,
    )
    rec_gloves_res = evaluate_fubgun_equipment_policy(gloves_res_delta, stage=BuildProgressionStage.LEVELING_15_32)
    assert rec_gloves_res.verdict == Verdict.EQUIP_NOW
    assert "+14% Fire Res" in rec_gloves_res.formatted_output


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
SAMPLE_BOOTS_RAW = """Item Class: Boots
Rarity: Rare
Beryl Stride
Mesh Greaves
--------
Armour: 50
--------
Requirements:
Level: 15
Str: 20
--------
Item Level: 18
--------
+25 to maximum Life
+15% to Cold Resistance
20% increased Movement Speed
"""


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


def test_generic_simulate_item_validates_slot_and_executes():
    """simulate_item accepts slot and candidate, validating the slot and calling engine with normalized slot."""
    fake_engine = FakePobEngine()
    fake_api = FakePoeApi()

    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=fake_api,
    )
    assert session.initialize() is True

    # Character description includes class and level
    assert session.character_desc == "BOMSHAK — Level 17 Mercenary"

    # Simulating invalid slot fails closed (raises ValueError)
    with pytest.raises(ValueError):
        session.simulate_item(slot="unknown_slot", raw_candidate=KRAKEN_DOME_RAW)

    # Simulating valid slot produces PobEquipmentDelta
    delta = session.simulate_item(slot="Helmet", raw_candidate=KRAKEN_DOME_RAW, candidate_name="Kraken Dome")
    assert delta is not None
    assert isinstance(delta, PobEquipmentDelta)
    assert delta.slot == "Helmet"
    assert delta.candidate_name == "Kraken Dome"
    assert delta.life_delta == 20
    assert delta.lightning_res_delta == 7
    assert delta.movement_speed_delta == 20.0


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


def test_backward_compatibility_facade_helmet_session():
    """Pob2HelmetSession is a thin facade over Pob2EquipmentSession preserving helmet properties and API."""
    fake_engine = FakePobEngine()
    fake_api = FakePoeApi()

    session = Pob2HelmetSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=fake_api,
    )
    assert isinstance(session, Pob2EquipmentSession)
    assert session.initialize() is True

    # Helmet-specific attributes are preserved
    assert session.current_helmet_name == "Brimstone Veil"
    assert session.current_helmet is not None
    assert session.current_helmet.get("name") == "Brimstone Veil"

    # simulate_candidate delegates to simulate_item for Helmet
    cid = session.submit_candidate(KRAKEN_DOME_RAW, candidate_name="Kraken Dome")
    delta = session.simulate_candidate(cid, KRAKEN_DOME_RAW, candidate_name="Kraken Dome")
    assert delta is not None
    assert isinstance(delta, PobHelmetDelta)
    assert delta.current_helmet_name == "Brimstone Veil"
    assert delta.life_delta == 20


def test_simulation_failure_restores_hot_engine_baseline():
    """A failed candidate calculation must not leave the hot engine on the candidate item."""

    class FailingStatsEngine(FakePobEngine):
        def __init__(self):
            super().__init__()
            self.fail_next_stats = False

        def call(self, action: str, **kwargs: Any) -> dict[str, Any]:
            if action == "calc_stats" and self.fail_next_stats:
                self.fail_next_stats = False
                raise RuntimeError("simulated PoB2 calculation failure")
            return super().call(action, **kwargs)

    fake_engine = FailingStatsEngine()
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True
    fake_engine.fail_next_stats = True

    candidate_id = session.submit_candidate(KRAKEN_DOME_RAW, candidate_name="Kraken Dome")
    assert session.simulate_item(
        slot="Helmet",
        raw_candidate=KRAKEN_DOME_RAW,
        candidate_id=candidate_id,
        candidate_name="Kraken Dome",
    ) is None
    assert fake_engine.call_log[-1] == "import_build"


def test_async_burst_coalescing_skips_stale_candidate_b():
    """Regression test for A -> B -> C burst behavior:
    1. A starts simulation (enters engine execution).
    2. While A is in-flight, B arrives and C arrives.
    3. A finishes simulation and is discarded as stale.
    4. B is already stale before simulation starts -> SKIP B (zero engine simulation calls).
    5. Simulate C only.
    """
    fake_engine = FakePobEngine(simulate_delay=0.05)
    fake_api = FakePoeApi()

    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=fake_api,
    )
    assert session.initialize() is True

    # 1. Candidate A arrives and starts simulating in a background thread
    id_a = session.submit_candidate(BRIMSTONE_VEIL_RAW, candidate_name="Candidate A")
    assert id_a == 1

    a_finished_delta: list[Any] = []
    a_started_event = threading.Event()

    def run_sim_a():
        a_started_event.set()
        delta = session.simulate_item("Helmet", BRIMSTONE_VEIL_RAW, candidate_id=id_a, candidate_name="Candidate A")
        a_finished_delta.append(delta)

    thread_a = threading.Thread(target=run_sim_a)
    thread_a.start()
    a_started_event.wait()
    # Allow thread A to acquire engine lock and enter simulation
    time.sleep(0.01)

    # 2. While A is in-flight, B and C arrive in burst
    id_b = session.submit_candidate(KRAKEN_DOME_RAW, candidate_name="Candidate B")
    assert id_b == 2
    id_c = session.submit_candidate(KRAKEN_DOME_RAW, candidate_name="Candidate C")
    assert id_c == 3

    # 3. Wait for A to finish
    thread_a.join()
    # A finished, but because C arrived while A was running, A was stale and discarded!
    assert len(a_finished_delta) == 1
    assert a_finished_delta[0] is None, "A was superseded by B and C, so A must be discarded"

    # Confirm A executed its simulation call on the engine
    equip_calls_after_a = fake_engine.call_log.count("equip_item")
    assert equip_calls_after_a == 1

    # 4. Now Candidate B attempts to simulate:
    # Since B is already stale before entering expensive simulation (id_b < latest_candidate_id),
    # B MUST BE SKIPPED without calling engine simulation!
    delta_b = session.simulate_item("Helmet", KRAKEN_DOME_RAW, candidate_id=id_b, candidate_name="Candidate B")
    assert delta_b is None, "B was stale before simulation starts, so B must be skipped"

    # Confirm engine equip_item was NOT called for B!
    equip_calls_after_b = fake_engine.call_log.count("equip_item")
    assert equip_calls_after_b == 1, "Candidate B must not waste engine simulation calls"

    # 5. Candidate C simulates: C is latest, so C simulates successfully!
    delta_c = session.simulate_item("Helmet", KRAKEN_DOME_RAW, candidate_id=id_c, candidate_name="Candidate C")
    assert delta_c is not None
    assert delta_c.candidate_id == id_c
    assert delta_c.candidate_name == "Candidate C"

    # Engine equip_item was called exactly once more for C
    equip_calls_after_c = fake_engine.call_log.count("equip_item")
    assert equip_calls_after_c == 2, "Only A and C should have invoked engine simulation"


RING_CANDIDATE_RAW = """Item Class: Rings
Rarity: Rare
Storm Loop
Iron Ring
--------
Requirements:
Level: 15
--------
+25 to maximum Life
+15% to Cold Resistance
"""

RING1_EQUIPPED_RAW = """Item Class: Rings
Rarity: Rare
Gloom Band
Iron Ring
--------
Requirements:
Level: 10
--------
+10 to maximum Life
"""

RING2_EQUIPPED_RAW = """Item Class: Rings
Rarity: Rare
Blood Coil
Coral Ring
--------
Requirements:
Level: 12
--------
+30 to maximum Life
+20% to Fire Resistance
"""


def test_pob2_production_slots_includes_rings():
    """POB2_PRODUCTION_SLOTS must include Ring 1 and Ring 2 for production PoB2 evaluation."""
    from companion.equipment.pob2_equipment_advisor import POB2_PRODUCTION_SLOTS
    assert "Ring 1" in POB2_PRODUCTION_SLOTS
    assert "Ring 2" in POB2_PRODUCTION_SLOTS


def test_pob2_production_slots_includes_weapons():
    """POB2_PRODUCTION_SLOTS must include canonical weapon slots for modular weapon subsystems."""
    from companion.equipment.pob2_equipment_advisor import (
        POB2_PRODUCTION_SLOTS,
        POB2_PRODUCTION_WEAPON_SLOTS,
    )
    for w_slot in ("Weapon 1", "Weapon 2", "Weapon 1 Swap", "Weapon 2 Swap"):
        assert w_slot in POB2_PRODUCTION_WEAPON_SLOTS
        assert w_slot in POB2_PRODUCTION_SLOTS



def test_simulate_ring_candidate_same_baseline_invariant():
    """Dual ring simulation must evaluate Ring 1 and Ring 2 from the exact same baseline, restoring baseline after each."""
    fake_engine = FakePobEngine()
    fake_engine.equipped_by_slot = {
        "Ring 1": {"equipped": True, "name": "Gloom Band", "raw": RING1_EQUIPPED_RAW},
        "Ring 2": {"equipped": True, "name": "Blood Coil", "raw": RING2_EQUIPPED_RAW},
    }
    fake_engine.defenses_by_slot = {
        "Ring 1": {"Life": 376, "Armour": 253, "Evasion": 70, "EnergyShield": 32, "TotalEHP": 305.0},
        "Ring 2": {"Life": 356, "Armour": 253, "Evasion": 70, "EnergyShield": 32, "TotalEHP": 280.0},
    }
    fake_engine.stats_by_slot = {
        "Ring 1": {
            "defense": {"FireResist": -35, "ColdResist": -35, "LightningResist": -43, "ChaosResist": 0, "MovementSpeed": 100.0},
            "offense": {"CombinedDPS": 29.07},
        },
        "Ring 2": {
            "defense": {"FireResist": -55, "ColdResist": -35, "LightningResist": -43, "ChaosResist": 0, "MovementSpeed": 100.0},
            "offense": {"CombinedDPS": 29.07},
        },
    }
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True

    # Initial call log reset for clean assertion
    fake_engine.call_log.clear()

    res = session.simulate_ring_candidate(raw_candidate=RING_CANDIDATE_RAW, candidate_name="Storm Loop")
    assert res is not None
    assert res.ring1_delta is not None
    assert res.ring2_delta is not None
    assert res.ring1_delta.slot == "Ring 1"
    assert res.ring2_delta.slot == "Ring 2"

    # Verify the exact execution pattern and baseline restorations:
    # 1. import_build (baseline) -> equip_item (Ring 1) -> get_defenses -> calc_stats -> import_build (restore)
    # 2. import_build (baseline) -> equip_item (Ring 2) -> get_defenses -> calc_stats -> import_build (restore)
    equip_indices = [i for i, call in enumerate(fake_engine.call_log) if call == "equip_item"]
    import_indices = [i for i, call in enumerate(fake_engine.call_log) if call == "import_build"]

    assert len(equip_indices) == 2, "Must equip candidate twice (once per ring slot)"
    assert len(import_indices) >= 3, "Baseline must be restored before/after each slot equip"
    # Ensure an import_build occurred between the two equip_item calls!
    assert any(equip_indices[0] < imp_idx < equip_indices[1] for imp_idx in import_indices), (
        "Baseline must be restored between Ring 1 and Ring 2 simulations"
    )
    # Ensure an import_build occurred after the second equip_item call!
    assert any(imp_idx > equip_indices[1] for imp_idx in import_indices), (
        "Baseline must be restored after Ring 2 simulation"
    )


def test_simulate_ring_candidate_returns_none_when_one_placement_fails():
    """A partial dual-ring result must not be sent to the policy evaluator."""
    class Ring2FailureEngine(FakePobEngine):
        def call(self, action: str, **kwargs: Any) -> dict[str, Any]:
            if action == "equip_item" and kwargs.get("slot") == "Ring 2":
                raise RuntimeError("ring 2 simulation failed")
            return super().call(action, **kwargs)

    fake_engine = Ring2FailureEngine()
    fake_engine.equipped_by_slot = {
        "Ring 1": {"equipped": True, "name": "Gloom Band", "raw": RING_CANDIDATE_RAW},
        "Ring 2": {"equipped": True, "name": "Blood Coil", "raw": RING_CANDIDATE_RAW},
    }
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True

    result = session.simulate_ring_candidate(RING_CANDIDATE_RAW, candidate_name="Storm Loop")

    assert result is None


def test_simulate_ring_candidate_skips_ring2_when_stale_after_ring1():
    """If a newer candidate arrives after Ring 1 simulation completes, Ring 2 MUST be skipped immediately."""
    fake_engine = FakePobEngine()
    fake_engine.equipped_by_slot = {
        "Ring 1": {"equipped": True, "name": "Gloom Band", "raw": RING1_EQUIPPED_RAW},
        "Ring 2": {"equipped": True, "name": "Blood Coil", "raw": RING2_EQUIPPED_RAW},
    }
    session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert session.initialize() is True

    cid_a = session.submit_candidate(RING_CANDIDATE_RAW, candidate_name="Candidate A")

    # Hook into fake_engine.call to inject candidate B right after Ring 1 finishes (during get_defenses or calc_stats)
    orig_call = fake_engine.call

    def side_effect(action: str, **kwargs):
        res = orig_call(action, **kwargs)
        if action == "equip_item" and kwargs.get("slot") == "Ring 1":
            # Candidate B arrives while Ring 1 equip is finishing!
            session.submit_candidate(RING_CANDIDATE_RAW, candidate_name="Candidate B")
        return res

    fake_engine.call = side_effect
    fake_engine.call_log.clear()

    res_a = session.simulate_ring_candidate(RING_CANDIDATE_RAW, candidate_id=cid_a, candidate_name="Candidate A")
    # A was detected as stale between Ring 1 and Ring 2, so it returns None
    assert res_a is None

    # Ring 1 was equipped, but Ring 2 MUST NOT have been called!
    assert fake_engine.call_log.count("equip_item") == 1, (
        "Candidate A was stale after Ring 1; Ring 2 simulation must be skipped to save engine time"
    )


def test_dual_ring_policy_clear_preference():
    """When one placement is an upgrade (EQUIP_NOW) and the other is a regression (REJECT), pick the upgrade."""
    from companion.equipment.fubgun_priorities import evaluate_dual_ring_policy
    from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
    from companion.equipment.recommendation import Verdict

    delta1 = PobEquipmentDelta(
        slot="Ring 1",
        candidate_id=1,
        candidate_name="Storm Loop",
        current_item_name="Gloom Band",
        life_delta=25,
        cold_res_delta=15,
        ehp_delta=30.0,
    )
    delta2 = PobEquipmentDelta(
        slot="Ring 2",
        candidate_id=1,
        candidate_name="Storm Loop",
        current_item_name="Blood Coil",
        life_delta=-30,
        fire_res_delta=-20,
        ehp_delta=-40.0,
    )

    rec = evaluate_dual_ring_policy(delta1, delta2)
    assert rec.ring1_recommendation.verdict == Verdict.EQUIP_NOW
    assert rec.ring2_recommendation.verdict == Verdict.REJECT
    assert rec.recommended_slot == "Ring 1"
    assert "Ring 1" in rec.summary_verdict
    assert "Vs Ring 1: Gloom Band" in rec.formatted_output
    assert "Vs Ring 2: Blood Coil" in rec.formatted_output
    assert "Recommended placement: Ring 1" in rec.formatted_output


def test_dual_ring_policy_empty_slot_as_known_pob_state():
    """Empty Ring 2 is treated as a known empty slot (not missing data), recommending equipping into EMPTY."""
    from companion.equipment.fubgun_priorities import evaluate_dual_ring_policy
    from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
    from companion.equipment.recommendation import Verdict

    delta1 = PobEquipmentDelta(
        slot="Ring 1",
        candidate_id=1,
        candidate_name="Storm Loop",
        current_item_name="Gloom Band",
        life_delta=-5,
        cold_res_delta=15,
        ehp_delta=10.0,
    )
    # Ring 2 was empty, so candidate gives pure positive stats without losing anything
    delta2 = PobEquipmentDelta(
        slot="Ring 2",
        candidate_id=1,
        candidate_name="Storm Loop",
        current_item_name=None,  # Empty slot
        life_delta=25,
        cold_res_delta=15,
        ehp_delta=50.0,
    )

    rec = evaluate_dual_ring_policy(delta1, delta2, empty_ring2=True)
    assert rec.ring2_recommendation.verdict == Verdict.EQUIP_NOW
    assert rec.recommended_slot == "Ring 2"
    assert "Vs Ring 2: EMPTY" in rec.formatted_output
    assert "Recommended placement: Ring 2 (slot is empty)" in rec.formatted_output


def test_dual_ring_policy_material_tradeoffs_neither_dominates():
    """When both placements are viable but trade different stats, do NOT invent a score; state both viable."""
    from companion.equipment.fubgun_priorities import evaluate_dual_ring_policy
    from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
    from companion.equipment.recommendation import Verdict

    # Ring 1 gains Life but loses Fire Res
    delta1 = PobEquipmentDelta(
        slot="Ring 1",
        candidate_id=1,
        candidate_name="Storm Loop",
        current_item_name="Ruby Ring",
        life_delta=30,
        fire_res_delta=-15,
        cold_res_delta=15,
        ehp_delta=15.0,
    )
    # Ring 2 gains Cold Res but loses Life
    delta2 = PobEquipmentDelta(
        slot="Ring 2",
        candidate_id=1,
        candidate_name="Storm Loop",
        current_item_name="Coral Ring",
        life_delta=-20,
        cold_res_delta=15,
        lightning_res_delta=20,
        ehp_delta=10.0,
    )

    rec = evaluate_dual_ring_policy(delta1, delta2)
    assert rec.recommended_slot is None
    assert rec.summary_verdict in (
        "Both placements viable / No safe automatic slot preference",
        "Neither placement recommended (keep current rings)",
    )
    assert len(rec.trade_off_notes) == 2


def test_dual_ring_policy_rejected_empty_slot_is_not_overwritten_by_pareto_dominance():
    """If an empty ring slot rejects the candidate, Pareto dominance must not overwrite it to replace the equipped ring."""
    from companion.equipment.fubgun_priorities import evaluate_dual_ring_policy
    from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
    from companion.equipment.recommendation import Verdict

    # Delta on Ring 1 has positive stats vs equipped Ring 1
    delta1 = PobEquipmentDelta(
        slot="Ring 1",
        candidate_id=1,
        candidate_name="Mediocre Band",
        current_item_name="Old Iron Ring",
        life_delta=15,
        cold_res_delta=10,
        ehp_delta=12.0,
    )
    # Delta on Ring 2 (empty) has zero gains, so rec2 is REJECT
    delta2 = PobEquipmentDelta(
        slot="Ring 2",
        candidate_id=1,
        candidate_name="Mediocre Band",
        current_item_name=None,
        life_delta=0,
        fire_res_delta=0,
        cold_res_delta=0,
        lightning_res_delta=0,
        chaos_res_delta=0,
        ehp_delta=0.0,
    )

    rec = evaluate_dual_ring_policy(delta1, delta2, empty_ring2=True, empty_ring1=False)
    assert rec.ring2_recommendation.verdict == Verdict.REJECT
    assert rec.recommended_slot is None
    assert "Neither placement recommended" in rec.summary_verdict
