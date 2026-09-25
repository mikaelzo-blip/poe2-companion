"""PoB2 Helmet Advisor Adapter and Mathematical Delta Provider.

RESPONSIBILITY BOUNDARY:
- Manages PoB2 MCP engine daemon session and character state in memory.
- Provides mathematical stat deltas between current equipped helmet and candidate helmet.
- Enforces async correctness: serialization/single-flight engine simulation, monotonically
  increasing candidate IDs, staleness tracking, and discarding stale candidate verdicts.
- Does NOT contain Fubgun campaign decision rules (rules live in fubgun_priorities.py).
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
from typing import Any, Callable
from pydantic import BaseModel, ConfigDict, Field


class PobHelmetDelta(BaseModel):
    """Mathematical stat deltas from PoB2 simulation."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    candidate_id: int
    candidate_name: str
    current_helmet_name: str | None = None
    life_delta: int = 0
    fire_res_delta: int = 0
    cold_res_delta: int = 0
    lightning_res_delta: int = 0
    chaos_res_delta: int = 0
    armour_delta: int = 0
    evasion_delta: int = 0
    es_delta: int = 0
    ehp_delta: float = 0.0
    dps_delta: float = 0.0
    life_before: int = 0
    life_after: int = 0
    ehp_before: float = 0.0
    ehp_after: float = 0.0
    dps_before: float = 0.0
    dps_after: float = 0.0


def resolve_pob2_backend_path(backend_path: str | Path | None = None) -> Path | None:
    """Resolve path to the path-of-building-2-mcp directory.

    Order of resolution:
    1. Explicit parameter if provided.
    2. Environment variable POB2_MCP_PATH.
    3. Auto-detected sibling directory `../path-of-building-2-mcp`.
    4. Default Windows development path `C:/Projects/path-of-building-2-mcp`.
    """
    if backend_path is not None:
        p = Path(backend_path)
        if (p / "server").exists() or (p / "pob_mcp").exists():
            return p
        return None

    env_path = os.environ.get("POB2_MCP_PATH")
    if env_path:
        p = Path(env_path)
        if (p / "server").exists() or (p / "pob_mcp").exists():
            return p

    # Sibling auto-detect from companion repo root
    try:
        repo_root = Path(__file__).resolve().parents[2]
        sibling = repo_root.parent / "path-of-building-2-mcp"
        if sibling.exists() and ((sibling / "server").exists() or (sibling / "pob_mcp").exists()):
            return sibling
    except Exception:
        pass

    default_p = Path("C:/Projects/path-of-building-2-mcp")
    if default_p.exists() and ((default_p / "server").exists() or (default_p / "pob_mcp").exists()):
        return default_p

    return None


class Pob2HelmetSession:
    """Session and adapter for headless PoB2 helmet calculations."""

    def __init__(
        self,
        character_name: str = "BOMSHAK",
        backend_path: str | Path | None = None,
        engine_factory: Callable[[], Any] | None = None,
        poe_api_client: Any = None,
        poe_oauth_client: Any = None,
    ):
        self.character_name = character_name
        self._raw_backend_path = backend_path
        self.backend_path = resolve_pob2_backend_path(backend_path)
        self.engine_factory = engine_factory
        self.poe_api_client = poe_api_client
        self.poe_oauth_client = poe_oauth_client

        self.is_available: bool = False
        self.unavailable_reason: str | None = None

        self.engine: Any = None
        self.xml: str | None = None
        self.current_helmet: dict[str, Any] | None = None
        self.current_helmet_name: str | None = None
        self.defenses_before: dict[str, Any] = {}
        self.stats_before: dict[str, Any] = {}

        # Concurrency & async correctness primitives
        self._engine_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._latest_candidate_id: int = 0
        self._displayed_candidate_id: int = 0

    def initialize(self) -> bool:
        """Initialize PoB2 engine and import target character.

        Returns True if successful, False if unavailable (with reason).
        """
        # If injectable mocks provided (e.g. in unit tests)
        if self.engine_factory is not None and self.poe_api_client is not None:
            try:
                self.engine = self.engine_factory()
                raw_json = self.poe_api_client.fetch_character_raw(self.character_name)
                imp_res = self.engine.call("import_character", json=raw_json)
                self.xml = imp_res.get("xml")
                self.current_helmet = self.engine.call("get_equipped", slot="Helmet")
                if self.current_helmet and self.current_helmet.get("equipped"):
                    self.current_helmet_name = self.current_helmet.get("name")
                self.defenses_before = self.engine.call("get_defenses")
                self.stats_before = self.engine.call("calc_stats")
                self.is_available = True
                return True
            except Exception as exc:
                self.is_available = False
                self.unavailable_reason = f"Initialization error: {exc}"
                return False

        # Live environment initialization
        if not self.backend_path:
            self.is_available = False
            self.unavailable_reason = (
                "PoB2 backend directory not found. Please set POB2_MCP_PATH or ensure "
                "path-of-building-2-mcp is a sibling directory."
            )
            return False

        server_dir = self.backend_path / "server"
        import_dir = server_dir if server_dir.exists() else self.backend_path
        if str(import_dir) not in sys.path:
            sys.path.insert(0, str(import_dir))

        try:
            from pob_mcp import poe_api, poe_oauth
            from pob_mcp.engine import PobEngine
        except Exception as exc:
            self.is_available = False
            self.unavailable_reason = f"Failed to import pob_mcp modules: {exc}"
            return False

        # Verify OAuth token
        try:
            token_str = poe_oauth.get_valid_token()
            if not token_str:
                self.is_available = False
                self.unavailable_reason = "PoE OAuth token missing or expired in %LOCALAPPDATA%/pob2-mcp/token.json"
                return False
        except Exception as exc:
            self.is_available = False
            self.unavailable_reason = f"OAuth verification error: {exc}"
            return False

        # Fetch character raw JSON
        try:
            raw_json = poe_api.fetch_character_raw(self.character_name)
        except Exception as exc:
            self.is_available = False
            self.unavailable_reason = f"Failed to fetch character '{self.character_name}' from GGG API: {exc}"
            return False

        # Boot PobEngine
        try:
            self.engine = PobEngine()
            self.engine.start()
        except Exception as exc:
            self.is_available = False
            self.unavailable_reason = f"Failed to start PoB2 Docker engine: {exc}"
            return False

        # Import character and setup initial baseline
        try:
            imp_res = self.engine.call("import_character", json=raw_json)
            self.xml = imp_res.get("xml")
            self.current_helmet = self.engine.call("get_equipped", slot="Helmet")
            if self.current_helmet and self.current_helmet.get("equipped"):
                self.current_helmet_name = self.current_helmet.get("name")
            self.defenses_before = self.engine.call("get_defenses")
            self.stats_before = self.engine.call("calc_stats")
            self.is_available = True
            return True
        except Exception as exc:
            self.is_available = False
            self.unavailable_reason = f"Failed to import character into PoB2: {exc}"
            return False

    def submit_candidate(self, candidate_raw: str, candidate_name: str = "") -> int:
        """Register a new clipboard candidate with a monotonically increasing ID."""
        with self._state_lock:
            self._latest_candidate_id += 1
            return self._latest_candidate_id

    def is_stale(self, candidate_id: int) -> bool:
        """Check if a candidate ID is superseded by a newer candidate."""
        with self._state_lock:
            return candidate_id < self._latest_candidate_id

    def simulate_candidate(
        self,
        candidate_id: int,
        candidate_raw: str,
        candidate_name: str = "",
    ) -> PobHelmetDelta | None:
        """Execute single-flight simulation for the candidate on hot PoB2 build.

        Returns PobHelmetDelta if fresh and calculated, or None if stale or unavailable.
        """
        if not self.is_available or self.engine is None or not self.xml:
            return None

        # Pre-check staleness before waiting for engine lock
        if self.is_stale(candidate_id):
            return None

        # Engine simulations MUST be serialized / single-flight
        with self._engine_lock:
            # Check staleness again after acquiring lock
            if self.is_stale(candidate_id):
                return None

            try:
                # 1. Restore baseline XML in case previous item mutated it
                self.engine.call("import_build", xml=self.xml)

                # 2. Equip candidate helmet
                self.engine.call("equip_item", slot="Helmet", raw=candidate_raw)

                # 3. Read post-equip defenses and stats
                def_after = self.engine.call("get_defenses")
                stats_after = self.engine.call("calc_stats")

                # 4. Restore baseline XML immediately so engine is pristine
                self.engine.call("import_build", xml=self.xml)

                # Post-check staleness before building delta
                if self.is_stale(candidate_id):
                    return None

                def_before = self.defenses_before
                stats_before = self.stats_before

                life_before = int(def_before.get("Life") or 0)
                life_after = int(def_after.get("Life") or 0)
                life_delta = life_after - life_before

                armour_delta = int((def_after.get("Armour") or 0) - (def_before.get("Armour") or 0))
                evasion_delta = int((def_after.get("Evasion") or 0) - (def_before.get("Evasion") or 0))
                es_delta = int((def_after.get("EnergyShield") or 0) - (def_before.get("EnergyShield") or 0))

                ehp_before = float(def_before.get("TotalEHP") or 0.0)
                ehp_after = float(def_after.get("TotalEHP") or 0.0)
                ehp_delta = ehp_after - ehp_before

                def_stats_before = stats_before.get("defense", {})
                def_stats_after = stats_after.get("defense", {})

                fire_delta = int((def_stats_after.get("FireResist") or 0) - (def_stats_before.get("FireResist") or 0))
                cold_delta = int((def_stats_after.get("ColdResist") or 0) - (def_stats_before.get("ColdResist") or 0))
                lightning_delta = int((def_stats_after.get("LightningResist") or 0) - (def_stats_before.get("LightningResist") or 0))
                chaos_delta = int((def_stats_after.get("ChaosResist") or 0) - (def_stats_before.get("ChaosResist") or 0))

                off_before = stats_before.get("offense", {})
                off_after = stats_after.get("offense", {})
                dps_before = float(off_before.get("CombinedDPS") or 0.0)
                dps_after = float(off_after.get("CombinedDPS") or 0.0)
                dps_delta = dps_after - dps_before

                return PobHelmetDelta(
                    candidate_id=candidate_id,
                    candidate_name=candidate_name or "Candidate Helmet",
                    current_helmet_name=self.current_helmet_name,
                    life_delta=life_delta,
                    fire_res_delta=fire_delta,
                    cold_res_delta=cold_delta,
                    lightning_res_delta=lightning_delta,
                    chaos_res_delta=chaos_delta,
                    armour_delta=armour_delta,
                    evasion_delta=evasion_delta,
                    es_delta=es_delta,
                    ehp_delta=ehp_delta,
                    dps_delta=dps_delta,
                    life_before=life_before,
                    life_after=life_after,
                    ehp_before=ehp_before,
                    ehp_after=ehp_after,
                    dps_before=dps_before,
                    dps_after=dps_after,
                )
            except Exception:
                return None

    def display_recommendation(
        self,
        delta: PobHelmetDelta | None,
        policy_evaluator: Callable[[PobHelmetDelta], Any],
    ) -> str | None:
        """Format and return final recommendation text if candidate is fresh.

        STALE RESULTS MUST NOT PRINT A FINAL VERDICT.
        Returns formatted text if fresh, or None if stale/discarded.
        """
        if delta is None:
            return None

        with self._state_lock:
            # Stale candidate check
            if delta.candidate_id < self._latest_candidate_id:
                return None
            # Do not re-display older candidate than already displayed
            if delta.candidate_id <= self._displayed_candidate_id:
                return None
            self._displayed_candidate_id = delta.candidate_id

        rec = policy_evaluator(delta)
        if hasattr(rec, "formatted_output"):
            return rec.formatted_output
        return str(rec)

    def close(self) -> None:
        """Clean up PoB engine."""
        with self._engine_lock:
            if self.engine is not None and hasattr(self.engine, "close"):
                try:
                    self.engine.close()
                except Exception:
                    pass
                self.engine = None
            self.is_available = False
