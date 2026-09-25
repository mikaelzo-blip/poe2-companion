"""Unit tests for PoB2 Helmet Advisor (RED stage).

Validates:
1. Separation of responsibilities: Pob2HelmetSession provides mathematical deltas only;
   canonical Fubgun policy in fubgun_priorities evaluates the verdict.
2. Configurable / auto-detected backend path (no hardcoded path).
3. Async correctness: serialized / single-flight simulation, monotonically increasing IDs,
   stale candidate rejection, and the regression test (A starts, B arrives, A finishes after B, only B displayed).
4. Configurable character selection (not hardcoded BOMSHAK).
5. Tolerant float comparisons for PoB metrics (EHP, DPS).
"""

from __future__ import annotations

import math
from pathlib import Path
import threading
import time
from typing import Any
import pytest

from companion.equipment.fubgun_priorities import (
    evaluate_fubgun_helmet_policy,
    FubgunHelmetRecommendation,
)
from companion.equipment.pob2_helmet_advisor import (
    Pob2HelmetSession,
    PobHelmetDelta,
    resolve_pob2_backend_path,
)
from companion.equipment.precedence import Verdict
from companion.equipment.rules import BuildProgressionStage

BRIMSTONE_VEIL_RAW = """Item Class: Helmets
Rarity: Rare
Brimstone Veil
Hewn Mask
--------
Evasion: 70
Energy Shield: 32
--------
Requirements:
Level: 17
Dex: 20
Int: 20
--------
Item Level: 17
--------
+32 to Evasion Rating
+11 to maximum Energy Shield
34% increased Evasion and Energy Shield
+36 to Accuracy Rating
+12 to maximum Mana
9% increased Rarity of Items found
3.9 Life Regeneration per second
10% increased Light Radius
"""

KRAKEN_DOME_RAW = """Item Class: Helmets
Rarity: Rare
Kraken Dome
Soldier Greathelm
--------
Armour: 45
--------
Requirements:
Level: 15
Str: 22
--------
Item Level: 19
--------
+20 to maximum Life
+7% to Lightning Resistance
1.2 Life Regenerated per second
"""


class FakePobEngine:
    """Mock PoB engine matching the JSON protocol of pob_mcp.engine.PobEngine."""

    def __init__(self, simulate_delay: float = 0.0):
        self.simulate_delay = simulate_delay
        self.call_log: list[str] = []
        self.in_flight_simulations: int = 0
        self.max_concurrent_simulations: int = 0
        self._lock = threading.Lock()
        self.equipped_helmet = {
            "equipped": True,
            "name": "Brimstone Veil",
            "raw": BRIMSTONE_VEIL_RAW,
        }
        self.defenses_before = {
            "Life": 361,
            "Armour": 253,
            "Evasion": 70,
            "EnergyShield": 32,
            "TotalEHP": 289.46,
        }
        self.stats_before = {
            "defense": {
                "FireResist": -35,
                "ColdResist": -50,
                "LightningResist": -43,
                "ChaosResist": 0,
                "MovementSpeed": 100.0,
            },
            "offense": {
                "CombinedDPS": 29.07,
            },
        }
        self.defenses_after = {
            "Life": 381,
            "Armour": 263,
            "Evasion": 70,
            "EnergyShield": 0,
            "TotalEHP": 296.20,
        }
        self.stats_after = {
            "defense": {
                "FireResist": -35,
                "ColdResist": -50,
                "LightningResist": -36,
                "ChaosResist": 0,
                "MovementSpeed": 120.0,
            },
            "offense": {
                "CombinedDPS": 27.25,
            },
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def call(self, action: str, **kwargs: Any) -> dict[str, Any]:
        with self._lock:
            self.call_log.append(action)

        if action == "import_character":
            return {
                "className": "Mercenary",
                "level": 17,
                "xml": "<PathOfBuilding><Build/></PathOfBuilding>",
            }
        elif action == "get_equipped":
            return self.equipped_helmet
        elif action == "get_defenses":
            return self.defenses_after if "equip_item" in self.call_log[-3:] else self.defenses_before
        elif action == "calc_stats":
            return self.stats_after if "equip_item" in self.call_log[-3:] else self.stats_before
        elif action == "equip_item":
            with self._lock:
                self.in_flight_simulations += 1
                if self.in_flight_simulations > self.max_concurrent_simulations:
                    self.max_concurrent_simulations = self.in_flight_simulations
            if self.simulate_delay > 0:
                time.sleep(self.simulate_delay)
            return {"success": True}
        elif action == "import_build":
            with self._lock:
                if self.in_flight_simulations > 0:
                    self.in_flight_simulations -= 1
            return {"success": True}
        return {"success": True}


class FakePoeApi:
    def fetch_character_raw(self, character_name: str) -> str:
        return f'{{"character": "{character_name}"}}'


def test_backend_path_resolution_and_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Path resolution supports custom path, env var, sibling auto-detect, and None fallback."""
    # 1. Direct explicit path
    custom_backend = tmp_path / "custom_pob2_mcp"
    (custom_backend / "server").mkdir(parents=True)
    resolved = resolve_pob2_backend_path(custom_backend)
    assert resolved == custom_backend

    # 2. Environment variable
    env_backend = tmp_path / "env_pob2_mcp"
    (env_backend / "server").mkdir(parents=True)
    monkeypatch.setenv("POB2_MCP_PATH", str(env_backend))
    assert resolve_pob2_backend_path(None) == env_backend

    # 3. None when missing
    monkeypatch.delenv("POB2_MCP_PATH", raising=False)
    assert resolve_pob2_backend_path(tmp_path / "nonexistent") is None


def test_configurable_character_name_initialization():
    """Character name is configurable and not hardcoded to BOMSHAK."""
    fake_engine = FakePobEngine()
    fake_api = FakePoeApi()

    session = Pob2HelmetSession(
        character_name="DaisyofWar",
        engine_factory=lambda: fake_engine,
        poe_api_client=fake_api,
    )
    assert session.character_name == "DaisyofWar"
    ok = session.initialize()
    assert ok is True
    assert session.is_available is True
    assert session.current_helmet_name == "Brimstone Veil"


def test_pob2_helmet_session_simulation_math_deltas():
    """Session produces mathematical PobHelmetDelta with tolerant floating comparisons."""
    fake_engine = FakePobEngine()
    fake_api = FakePoeApi()

    session = Pob2HelmetSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=fake_api,
    )
    assert session.initialize() is True

    cid = session.submit_candidate(KRAKEN_DOME_RAW, candidate_name="Kraken Dome")
    assert cid == 1

    delta = session.simulate_candidate(cid, KRAKEN_DOME_RAW, candidate_name="Kraken Dome")
    assert delta is not None
    assert isinstance(delta, PobHelmetDelta)
    assert delta.candidate_id == 1
    assert delta.candidate_name == "Kraken Dome"
    assert delta.current_helmet_name == "Brimstone Veil"
    assert delta.life_delta == 20
    assert delta.lightning_res_delta == 7
    assert delta.armour_delta == 10
    assert delta.es_delta == -32
    # Tolerant floating comparisons as required by Correction 5
    assert math.isclose(delta.ehp_delta, 6.74, abs_tol=0.1)
    assert math.isclose(delta.dps_delta, -1.82, abs_tol=0.1)


def test_fubgun_helmet_policy_favors_kraken_dome_over_brimstone_veil():
    """Fubgun policy in canonical fubgun_priorities evaluates delta and recommends EQUIP_NOW."""
    delta = PobHelmetDelta(
        candidate_id=1,
        candidate_name="Kraken Dome",
        current_helmet_name="Brimstone Veil",
        life_delta=20,
        fire_res_delta=0,
        cold_res_delta=0,
        lightning_res_delta=7,
        chaos_res_delta=0,
        armour_delta=10,
        evasion_delta=0,
        es_delta=-32,
        ehp_delta=6.74,
        dps_delta=-1.82,
        life_before=361,
        life_after=381,
        ehp_before=289.46,
        ehp_after=296.20,
        dps_before=29.07,
        dps_after=27.25,
    )

    rec = evaluate_fubgun_helmet_policy(delta, stage=BuildProgressionStage.LEVELING_15_32)
    assert isinstance(rec, FubgunHelmetRecommendation)
    assert rec.verdict == Verdict.EQUIP_NOW
    assert "Resistance > Life" in rec.reason
    assert "accuracy" in rec.reason.lower() or "accuracy" in "\n".join(rec.trade_offs).lower()
    # Check that recommendation text contains key elements
    rendered = rec.formatted_output
    assert "🟢 EQUIP NOW" in rendered
    assert "Kraken Dome" in rendered
    assert "+20 Life" in rendered
    assert "+7% Lightning Res" in rendered


def test_async_correctness_serialized_single_flight():
    """PoB engine simulations must be serialized / single-flight under concurrency."""
    fake_engine = FakePobEngine(simulate_delay=0.05)
    fake_api = FakePoeApi()

    session = Pob2HelmetSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=fake_api,
    )
    assert session.initialize() is True

    # Run simulations across multiple threads simultaneously
    def run_sim(item_id: int):
        session.simulate_candidate(item_id, KRAKEN_DOME_RAW, candidate_name=f"Candidate {item_id}")

    threads = [threading.Thread(target=run_sim, args=(i,)) for i in range(1, 5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # The engine must NEVER have had concurrent simulations mutating the hot build
    assert fake_engine.max_concurrent_simulations == 1


def test_async_correctness_regression_candidate_a_finishes_after_b_only_b_displayed():
    """Regression test:
    Candidate A starts.
    Candidate B arrives while candidate A is in-flight (making A stale).
    Under serialized single-flight execution, candidate A finishes but is detected
    as stale and discarded; only Candidate B becomes the displayed final recommendation.
    """
    fake_engine = FakePobEngine()
    fake_api = FakePoeApi()

    session = Pob2HelmetSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=fake_api,
    )
    assert session.initialize() is True

    displayed_verdicts: list[str] = []

    def mock_output_writer(text: str):
        displayed_verdicts.append(text)

    # 1. Candidate A starts
    id_a = session.submit_candidate(BRIMSTONE_VEIL_RAW, candidate_name="Candidate A")
    assert id_a == 1

    # 2. Candidate B arrives
    id_b = session.submit_candidate(KRAKEN_DOME_RAW, candidate_name="Candidate B")
    assert id_b == 2

    # 3. Candidate B simulates and finishes
    delta_b = session.simulate_candidate(id_b, KRAKEN_DOME_RAW, candidate_name="Candidate B")
    assert delta_b is not None
    assert delta_b.candidate_id == 2

    rec_b = session.display_recommendation(
        delta_b,
        policy_evaluator=lambda d: evaluate_fubgun_helmet_policy(d, stage=BuildProgressionStage.LEVELING_15_32),
    )
    assert rec_b is not None
    mock_output_writer(rec_b)

    # 4. Candidate A finishes AFTER candidate B
    delta_a = session.simulate_candidate(id_a, BRIMSTONE_VEIL_RAW, candidate_name="Candidate A")
    # Even if delta_a was returned or completed late:
    rec_a = session.display_recommendation(
        delta_a,
        policy_evaluator=lambda d: evaluate_fubgun_helmet_policy(d, stage=BuildProgressionStage.LEVELING_15_32),
    )

    # 5. Candidate A MUST NOT print a final verdict because it is stale!
    assert rec_a is None

    # Verify only candidate B was displayed
    assert len(displayed_verdicts) == 1
    assert "Candidate B" in displayed_verdicts[0]
    assert "Candidate A" not in displayed_verdicts[0]


def test_async_concurrent_threads_race_only_newer_candidate_displays():
    """True multi-threaded race test:
    Thread A starts simulating candidate A with a deliberate delay.
    Candidate B arrives on Thread B while Thread A is running.
    Thread B finishes and displays.
    Thread A finally finishes its simulation, but is detected as stale and discarded.
    """
    fake_engine = FakePobEngine()
    fake_api = FakePoeApi()

    session = Pob2HelmetSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=fake_api,
    )
    assert session.initialize() is True

    displayed_results: list[str] = []
    thread_a_started = threading.Event()

    def worker_a(item_id: int):
        # Notify that A has started
        thread_a_started.set()
        # Simulate deliberate delay in calculation
        time.sleep(0.08)
        delta = session.simulate_candidate(item_id, BRIMSTONE_VEIL_RAW, candidate_name="Candidate A")
        res = session.display_recommendation(
            delta,
            policy_evaluator=lambda d: evaluate_fubgun_helmet_policy(d, stage=BuildProgressionStage.LEVELING_15_32),
        )
        if res is not None:
            displayed_results.append(res)

    def worker_b(item_id: int):
        delta = session.simulate_candidate(item_id, KRAKEN_DOME_RAW, candidate_name="Candidate B")
        res = session.display_recommendation(
            delta,
            policy_evaluator=lambda d: evaluate_fubgun_helmet_policy(d, stage=BuildProgressionStage.LEVELING_15_32),
        )
        if res is not None:
            displayed_results.append(res)

    # 1. Candidate A starts
    id_a = session.submit_candidate(BRIMSTONE_VEIL_RAW, candidate_name="Candidate A")
    t_a = threading.Thread(target=worker_a, args=(id_a,))
    t_a.start()

    # Wait for Thread A to actually begin
    thread_a_started.wait()

    # 2. Candidate B arrives while A is running
    id_b = session.submit_candidate(KRAKEN_DOME_RAW, candidate_name="Candidate B")
    t_b = threading.Thread(target=worker_b, args=(id_b,))
    t_b.start()

    t_b.join()
    t_a.join()

    # Only Candidate B must be displayed!
    assert len(displayed_results) == 1
    assert "Candidate B" in displayed_results[0]
    assert "Candidate A" not in displayed_results[0]


def test_graceful_fallback_when_pob2_unavailable(tmp_path: Path):
    """Graceful fallback when engine cannot boot or backend is missing."""
    session = Pob2HelmetSession(
        character_name="BOMSHAK",
        backend_path=tmp_path / "nonexistent",
    )
    ok = session.initialize()
    assert ok is False
    assert session.is_available is False
    assert session.unavailable_reason is not None
    assert "not found" in session.unavailable_reason.lower() or "unavailable" in session.unavailable_reason.lower()
