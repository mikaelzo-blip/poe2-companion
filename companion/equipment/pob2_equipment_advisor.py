"""PoB2 Generic Equipment Advisor Foundation and Mathematical Delta Provider.

RESPONSIBILITY BOUNDARY:
- Manages PoB2 MCP engine daemon session and character state in memory.
- Provides canonical slot normalization, validation, and generic item simulation.
- Enforces async correctness: serialized/single-flight engine simulation, monotonically
  increasing candidate IDs, staleness tracking, latest-wins candidate coalescing,
  and thread-safe bookkeeping independent of engine lock.
- Generic across equipment slots conceptually (simulate_item(slot, raw_candidate)).
- Production live watcher routing is explicitly allowlisted for the verified core slots.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
from typing import Any, Callable
from pydantic import BaseModel, ConfigDict, Field

from companion.equipment.schema import SlotType


CANONICAL_EQUIPMENT_SLOTS: set[str] = {
    "Helmet",
    "Body Armour",
    "Gloves",
    "Boots",
    "Amulet",
    "Ring 1",
    "Ring 2",
    "Belt",
    "Weapon 1",
    "Weapon 2",
}

# Production routing is narrower than the generic slot foundation. Rings and weapons
# remain native-policy only until their slot-context milestones are verified.
POB2_PRODUCTION_SLOTS: frozenset[str] = frozenset(
    {"Helmet", "Body Armour", "Gloves", "Boots", "Belt", "Amulet"}
)

_SLOT_ALIAS_MAP: dict[str, str] = {
    "helmet": "Helmet",
    "helm": "Helmet",
    "head": "Helmet",
    "boots": "Boots",
    "boot": "Boots",
    "shoes": "Boots",
    "gloves": "Gloves",
    "glove": "Gloves",
    "body_armour": "Body Armour",
    "body armour": "Body Armour",
    "bodyarmour": "Body Armour",
    "chest": "Body Armour",
    "armour": "Body Armour",
    "amulet": "Amulet",
    "necklace": "Amulet",
    "belt": "Belt",
    "ring1": "Ring 1",
    "ring_1": "Ring 1",
    "ring 1": "Ring 1",
    "ring2": "Ring 2",
    "ring_2": "Ring 2",
    "ring 2": "Ring 2",
    "weapon1": "Weapon 1",
    "weapon_1": "Weapon 1",
    "weapon 1": "Weapon 1",
    "main_hand": "Weapon 1",
    "main hand": "Weapon 1",
    "weapon2": "Weapon 2",
    "weapon_2": "Weapon 2",
    "weapon 2": "Weapon 2",
    "off_hand": "Weapon 2",
    "off hand": "Weapon 2",
}


def normalize_and_validate_pob_slot(slot: str | SlotType) -> str:
    """Normalize and validate an equipment slot to its canonical PoB2 slot representation.

    Fails closed (raises ValueError) if the slot is unknown, malformed, or unsupported.
    """
    if isinstance(slot, SlotType):
        raw_val = slot.value
    elif isinstance(slot, str):
        raw_val = slot.strip()
    else:
        raise ValueError(f"Unknown or unsupported equipment slot: {slot!r}")

    if not raw_val:
        raise ValueError("Unknown or unsupported equipment slot: slot identifier cannot be empty")

    # Direct match in canonical set
    if raw_val in CANONICAL_EQUIPMENT_SLOTS:
        return raw_val

    # Normalized lookup in alias map
    lookup_key = raw_val.lower().replace("-", "_")
    normalized = _SLOT_ALIAS_MAP.get(lookup_key)
    if normalized and normalized in CANONICAL_EQUIPMENT_SLOTS:
        return normalized

    # Title case fallback check
    title_val = raw_val.title()
    if title_val in CANONICAL_EQUIPMENT_SLOTS:
        return title_val

    raise ValueError(f"Unknown or unsupported equipment slot: {slot!r}")


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


class PobEquipmentDelta(BaseModel):
    """Mathematical stat deltas from PoB2 simulation for any equipment slot."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    slot: str
    candidate_id: int
    candidate_name: str
    current_item_name: str | None = None
    current_helmet_name: str | None = None
    life_delta: int = 0
    fire_res_delta: int = 0
    cold_res_delta: int = 0
    lightning_res_delta: int = 0
    chaos_res_delta: int = 0
    armour_delta: int = 0
    evasion_delta: int = 0
    es_delta: int = 0
    movement_speed_delta: float = 0.0
    ehp_delta: float = 0.0
    dps_delta: float = 0.0
    life_before: int = 0
    life_after: int = 0
    ehp_before: float = 0.0
    ehp_after: float = 0.0
    dps_before: float = 0.0
    dps_after: float = 0.0


class Pob2EquipmentSession:
    """Generic session and adapter for headless PoB2 equipment calculations.

    Features:
    - Canonical slot normalization & validation (fails closed on unknown slots).
    - Serialized single-flight simulation on the hot PoB2 build via `_engine_lock`.
    - Thread-safe request bookkeeping (IDs, staleness) via independent `_state_lock`.
    - Latest-wins candidate coalescing before entering expensive simulation.
    """

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
        self.class_name: str | None = None
        self.level: int | None = None
        self.equipped_items: dict[str, dict[str, Any]] = {}
        self.defenses_before: dict[str, Any] = {}
        self.stats_before: dict[str, Any] = {}

        # Concurrency & async correctness primitives
        # _engine_lock ONLY serializes expensive PoB engine simulation calls
        self._engine_lock = threading.Lock()
        # _state_lock synchronizes request ID generation and staleness bookkeeping independently
        self._state_lock = threading.Lock()
        self._latest_candidate_id: int = 0
        self._displayed_candidate_id: int = 0

    @property
    def character_desc(self) -> str:
        """Formatted character description, e.g. 'BOMSHAK — Level 17 Mercenary'."""
        parts = []
        if self.level is not None:
            parts.append(f"Level {self.level}")
        if self.class_name:
            parts.append(self.class_name)
        if parts:
            return f"{self.character_name} — {' '.join(parts)}"
        return self.character_name

    def initialize(self) -> bool:
        """Initialize PoB2 engine and import target character.

        Returns True if successful, False if unavailable (with reason).
        """
        # Injectable mocks (e.g. in unit tests)
        if self.engine_factory is not None and self.poe_api_client is not None:
            try:
                self.engine = self.engine_factory()
                raw_json = self.poe_api_client.fetch_character_raw(self.character_name)
                imp_res = self.engine.call("import_character", json=raw_json)
                self.xml = imp_res.get("xml")
                self.class_name = imp_res.get("className")
                self.level = imp_res.get("level")

                # Query each production-enabled core slot once while the imported build is hot.
                for slot in POB2_PRODUCTION_SLOTS:
                    equipped = self.engine.call("get_equipped", slot=slot)
                    if equipped:
                        self.equipped_items[slot] = equipped

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
            self.class_name = imp_res.get("className")
            self.level = imp_res.get("level")

            for slot in POB2_PRODUCTION_SLOTS:
                equipped = self.engine.call("get_equipped", slot=slot)
                if equipped:
                    self.equipped_items[slot] = equipped

            self.defenses_before = self.engine.call("get_defenses")
            self.stats_before = self.engine.call("calc_stats")
            self.is_available = True
            return True
        except Exception as exc:
            self.is_available = False
            self.unavailable_reason = f"Failed to import character into PoB2: {exc}"
            return False

    def submit_candidate(self, candidate_raw: str, candidate_name: str = "", slot: str = "Helmet") -> int:
        """Register a new clipboard candidate with a monotonically increasing ID.

        Synchronized via `_state_lock` without blocking on `_engine_lock`.
        """
        with self._state_lock:
            self._latest_candidate_id += 1
            return self._latest_candidate_id

    def is_stale(self, candidate_id: int) -> bool:
        """Check if a candidate ID is superseded by a newer candidate.

        Synchronized via `_state_lock` without blocking on `_engine_lock`.
        """
        with self._state_lock:
            return candidate_id < self._latest_candidate_id

    def get_equipped_item(self, slot: str) -> dict[str, Any] | None:
        """Get equipped item dictionary for canonical slot."""
        canonical_slot = normalize_and_validate_pob_slot(slot)
        if canonical_slot in self.equipped_items:
            return self.equipped_items[canonical_slot]
        if self.is_available and self.engine is not None:
            try:
                item = self.engine.call("get_equipped", slot=canonical_slot)
                if item:
                    self.equipped_items[canonical_slot] = item
                    return item
            except Exception:
                pass
        return None

    def get_current_item_name(self, slot: str) -> str | None:
        """Get the current equipped item name for a given slot."""
        item = self.get_equipped_item(slot)
        if item and item.get("equipped"):
            return item.get("name")
        return None

    def simulate_item(
        self,
        slot: str | SlotType,
        raw_candidate: str,
        candidate_id: int | None = None,
        candidate_name: str = "",
    ) -> PobEquipmentDelta | None:
        """Execute single-flight simulation for any canonical equipment slot on hot PoB2 build.

        Enforces:
        - Canonical slot validation (fails closed with ValueError on unknown slots).
        - Latest-wins candidate coalescing before entering expensive simulation.
        - Single-flight serialization on engine lock.
        - Baseline XML restoration before and after equip.

        Returns PobEquipmentDelta if fresh and calculated, or None if stale or unavailable.
        """
        canonical_slot = normalize_and_validate_pob_slot(slot)

        if candidate_id is None:
            candidate_id = self.submit_candidate(raw_candidate, candidate_name=candidate_name, slot=canonical_slot)

        if not self.is_available or self.engine is None or not self.xml:
            return None

        # 1. Pre-check staleness before waiting for expensive engine lock (skip if already superseded)
        if self.is_stale(candidate_id):
            return None

        # 2. Acquire engine lock for serialized single-flight simulation
        with self._engine_lock:
            # Re-check staleness immediately upon acquiring lock:
            # If a newer candidate arrived while waiting for the lock, SKIP THIS SIMULATION!
            if self.is_stale(candidate_id):
                return None

            candidate_applied = False
            try:
                # 2a. Restore baseline XML in case previous item mutated it
                self.engine.call("import_build", xml=self.xml)

                # 2b. Equip candidate item in canonical slot
                candidate_applied = True
                self.engine.call("equip_item", slot=canonical_slot, raw=raw_candidate)

                # 2c. Read post-equip defenses and stats
                def_after = self.engine.call("get_defenses")
                stats_after = self.engine.call("calc_stats")

                # 2d. Restore baseline XML immediately so engine is pristine
                self.engine.call("import_build", xml=self.xml)
                candidate_applied = False

                # 2e. Post-check staleness before building delta
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
                movement_speed_delta = float(
                    (def_stats_after.get("MovementSpeed") or 0.0)
                    - (def_stats_before.get("MovementSpeed") or 0.0)
                )

                off_before = stats_before.get("offense", {})
                off_after = stats_after.get("offense", {})
                dps_before = float(off_before.get("CombinedDPS") or 0.0)
                dps_after = float(off_after.get("CombinedDPS") or 0.0)
                dps_delta = dps_after - dps_before

                cur_name = self.get_current_item_name(canonical_slot)

                return PobEquipmentDelta(
                    slot=canonical_slot,
                    candidate_id=candidate_id,
                    candidate_name=candidate_name or f"Candidate {canonical_slot}",
                    current_item_name=cur_name,
                    current_helmet_name=cur_name if canonical_slot == "Helmet" else None,
                    life_delta=life_delta,
                    fire_res_delta=fire_delta,
                    cold_res_delta=cold_delta,
                    lightning_res_delta=lightning_delta,
                    chaos_res_delta=chaos_delta,
                    armour_delta=armour_delta,
                    evasion_delta=evasion_delta,
                    es_delta=es_delta,
                    movement_speed_delta=movement_speed_delta,
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
            finally:
                if candidate_applied:
                    try:
                        self.engine.call("import_build", xml=self.xml)
                    except Exception:
                        pass

    def display_recommendation(
        self,
        delta: PobEquipmentDelta | None,
        policy_evaluator: Callable[[PobEquipmentDelta], Any],
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
