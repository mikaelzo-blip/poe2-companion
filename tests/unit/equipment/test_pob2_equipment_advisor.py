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
    Pob2EquipmentSession,
    PobEquipmentDelta,
    normalize_and_validate_pob_slot,
)
from companion.equipment.pob2_helmet_advisor import (
    Pob2HelmetSession,
    PobHelmetDelta,
)
from companion.equipment.schema import SlotType
from tests.unit.equipment.test_pob2_helmet_advisor import (
    BRIMSTONE_VEIL_RAW,
    KRAKEN_DOME_RAW,
    FakePobEngine,
    FakePoeApi,
)

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

