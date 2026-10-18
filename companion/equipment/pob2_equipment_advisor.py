"""PoB2 Generic Equipment Advisor Foundation and Mathematical Delta Provider.

RESPONSIBILITY BOUNDARY:
- Manages PoB2 MCP engine daemon session and character state in memory.
- Provides canonical slot normalization, validation, and generic item simulation.
- Enforces async correctness: serialized/single-flight engine simulation, monotonically
  increasing candidate IDs, staleness tracking, latest-wins candidate coalescing,
  and thread-safe bookkeeping independent of engine lock.
- Generic across equipment slots conceptually.
- Production slot routing is explicitly allowlisted for the verified core slots.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
import sys
import threading
import time
from typing import Any, Callable
from pydantic import BaseModel, ConfigDict, Field

from companion.equipment.schema import SlotType

logger = logging.getLogger(__name__)


def load_pob_mcp_modules(backend_path: Path | None = None) -> tuple[Any, Any] | None:
    """Import (poe_api, poe_oauth) from the PoB2 MCP backend; None if missing or broken."""
    backend_path = backend_path or resolve_pob2_backend_path()
    if not backend_path:
        return None
    server_dir = backend_path / "server"
    import_dir = server_dir if server_dir.exists() else backend_path
    if str(import_dir) not in sys.path:
        sys.path.insert(0, str(import_dir))
    try:
        from pob_mcp import poe_api, poe_oauth
    except Exception:
        logger.warning("Failed to import pob_mcp modules from %s", import_dir, exc_info=True)
        return None
    return poe_api, poe_oauth

try:
    from pob_mcp.engine import EngineError, EngineTimeoutError
except ImportError:
    class EngineError(RuntimeError):
        """Raised when the PoB2 engine process fails to start or a command errors."""

    class EngineTimeoutError(EngineError):
        """Raised when an engine IPC call exceeds call_timeout."""


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
    "Weapon 1 Swap",
    "Weapon 2 Swap",
}

POB2_PRODUCTION_CORE_SLOTS: frozenset[str] = frozenset(
    {"Helmet", "Body Armour", "Gloves", "Boots", "Belt", "Amulet"}
)
POB2_PRODUCTION_RING_SLOTS: frozenset[str] = frozenset({"Ring 1", "Ring 2"})
POB2_PRODUCTION_WEAPON_SLOTS: frozenset[str] = frozenset(
    {"Weapon 1", "Weapon 2", "Weapon 1 Swap", "Weapon 2 Swap"}
)
POB2_PRODUCTION_SLOTS: frozenset[str] = (
    POB2_PRODUCTION_CORE_SLOTS | POB2_PRODUCTION_RING_SLOTS | POB2_PRODUCTION_WEAPON_SLOTS
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
    "weapon1_swap": "Weapon 1 Swap",
    "weapon_1_swap": "Weapon 1 Swap",
    "weapon 1 swap": "Weapon 1 Swap",
    "main_hand_swap": "Weapon 1 Swap",
    "weapon2_swap": "Weapon 2 Swap",
    "weapon_2_swap": "Weapon 2 Swap",
    "weapon 2 swap": "Weapon 2 Swap",
    "off_hand_swap": "Weapon 2 Swap",
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


def _set_weapon_set_in_xml(xml_str: str, set_num: int) -> str:
    """Toggle useSecondWeaponSet ('true' for Set 2, 'false' for Set 1) in PoB XML."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_str)
        items = root.find("Items")
        val = "true" if set_num == 2 else "false"
        if items is None:
            items = ET.SubElement(root, "Items")
        items.set("useSecondWeaponSet", val)
        isets = items.findall("ItemSet")
        if not isets:
            ET.SubElement(items, "ItemSet", {"id": "1", "useSecondWeaponSet": val})
        else:
            for iset in isets:
                iset.set("useSecondWeaponSet", val)
        return ET.tostring(root, encoding="unicode")
    except Exception:
        return xml_str


def _as_payload(raw_json: Any) -> dict[str, Any] | None:
    """GGG character JSON (string or dict) as a dict; None when it is not a JSON object."""
    try:
        payload = json.loads(raw_json) if isinstance(raw_json, (str, bytes)) else raw_json
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _main_dps(engine: Any, group: int) -> float:
    """Make ``group`` PoB's main skill and return its DPS (FullDPS, else CombinedDPS)."""
    return float((engine.call("set_main_skill", group=group) or {}).get("mainDPS") or 0)


@lru_cache(maxsize=1)
def _zone_acts() -> dict[str, Any]:
    # Generated from the PoB fork's Data/WorldAreas.lua by scripts/gen_zone_acts.py.
    return json.loads((Path(__file__).parent / "data" / "zone_acts.json").read_text(encoding="utf-8"))


def act_of_zone(zone: str | None) -> int | None:
    """Act of a campaign zone (interludes = 6, endgame areas = 10); None for hideouts, maps and unknown names."""
    return _zone_acts()["zones"].get(zone or "")


def act_for_level(level: int | None) -> int | None:
    """Campaign act whose areas start at or below ``level`` (an estimate when the zone is unknown)."""
    if level is None:
        return None
    acts = [int(a) for a, lv in _zone_acts()["act_min_level"].items() if int(a) < 10 and lv <= level]
    return max(acts, default=1)


def resist_penalty_for_act(act: int | None) -> int | None:
    """PoB's elemental resistance penalty for ``act`` (Act 1 = 0 ... endgame = -60)."""
    return None if act is None else max(-10 * (act - 1), -60)


def resist_penalty_for_zone(zone: str | None) -> int | None:
    """PoB's elemental resistance penalty for the act of ``zone``; None if unknown."""
    return resist_penalty_for_act(act_of_zone(zone))


def _set_resist_penalty_in_xml(xml_str: str, penalty: int) -> str:
    """Write PoB's ``resistancePenalty`` config input (absent = endgame -60) into the active config set."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_str)
    config = root.find("Config")
    if config is None:
        config = ET.SubElement(root, "Config", {"activeConfigSet": "1"})
    active = config.get("activeConfigSet", "1")
    target = next((cs for cs in config.findall("ConfigSet") if cs.get("id") == active), None)
    if target is None:
        target = config if not config.findall("ConfigSet") else ET.SubElement(config, "ConfigSet", {"id": active})
    for node in target.findall("Input"):
        if node.get("name") == "resistancePenalty":
            target.remove(node)
    ET.SubElement(target, "Input", {"name": "resistancePenalty", "number": str(penalty)})
    return ET.tostring(root, encoding="unicode")


def _skill_index(engine: Any) -> dict[str, int]:
    """Active skill name -> socket group index in the build loaded right now.

    ponytail: two groups with the same active skill collapse to the first one.
    """
    groups = (engine.call("list_skills") or {}).get("groups") or []
    return {g["activeSkill"]: g["index"] for g in reversed(groups) if g.get("activeSkill")}


def _clear_slots_in_xml(xml_str: str, clear_slots: tuple[str, ...] | list[str]) -> str:
    """Clear specific slot itemIds (set to 0) in PoB XML."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_str)
        requested = set(clear_slots)
        for slot in root.iter("Slot"):
            if slot.get("name") in requested and slot.get("itemId") is not None:
                slot.set("itemId", "0")
        return ET.tostring(root, encoding="unicode")
    except (ET.ParseError, TypeError):
        return xml_str


_RES_KEYS = {
    "fire": "FireResist",
    "cold": "ColdResist",
    "lightning": "LightningResist",
    "chaos": "ChaosResist",
}


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
    strength_delta: int = 0
    dexterity_delta: int = 0
    intelligence_delta: int = 0
    mana_delta: int = 0
    crit_chance_delta: float = 0.0  # percentage points
    crit_bonus_delta: float = 0.0  # Critical Damage Bonus, percentage points
    average_hit_pct: float = 0.0  # percent change of the main skill's Average Hit
    speed_pct: float = 0.0  # percent change of the main skill's uses per second
    life_before: int = 0
    life_after: int = 0
    ehp_before: float = 0.0
    ehp_after: float = 0.0
    dps_before: float = 0.0
    dps_after: float = 0.0
    res_before: dict[str, float] = {}  # keys: fire, cold, lightning, chaos
    res_after: dict[str, float] = {}


def is_docker_daemon_running() -> bool:
    """Check if Docker daemon is responsive in <10ms without blocking."""
    import sys
    if sys.platform == "win32":
        return os.path.exists(r"\\.\pipe\docker_engine") or os.path.exists(r"\\.\pipe\dockerDesktopLinuxEngine")
    sock_path = Path("/var/run/docker.sock")
    user_sock = Path.home() / ".docker/run/docker.sock"
    return sock_path.exists() or user_sock.exists()


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
        self.is_healthy: bool = True
        self.unhealthy_reason: str | None = None

        self.engine: Any = None
        self.sandbox_engine: Any = None
        self.xml: str | None = None
        # GGG character payload of the last import; its item text beats PoB's BuildRaw text
        self.ggg_payload: dict[str, Any] | None = None
        self.class_name: str | None = None
        self.level: int | None = None
        self.last_synced_at: float = 0.0
        self._last_zone: str | None = None
        self.last_refresh_attempt_at: float = float("-inf")
        self._handed_level: int | None = None
        self.equipped_items: dict[str, dict[str, Any]] = {}
        self.defenses_before: dict[str, Any] = {}
        self.stats_before: dict[str, Any] = {}
        # 1-based main socket group reported by PoB after each import; locked on every measurement
        self.main_group: int | None = None
        # enabled socket groups with an active skill (1-based), from the same refresh
        self.skill_groups: list[int] = []
        # elemental resistance penalty of the character's act, written into self.xml (None = PoB's endgame default)
        self.resist_penalty: int | None = None

        # Concurrency & async correctness primitives
        # _engine_lock ONLY serializes expensive PoB engine simulation calls
        self._engine_lock = threading.Lock()
        # _state_lock synchronizes request ID generation and staleness bookkeeping independently
        self._state_lock = threading.Lock()
        self._latest_candidate_id: int = 0
        self._latest_by_source: dict[str, int] = {}

    def initialize(self) -> bool:
        """Initialize PoB2 engine and import target character.

        Returns True if successful, False if unavailable (with reason).
        """
        # Injectable mocks (e.g. in unit tests)
        if self.engine_factory is not None and self.poe_api_client is not None:
            try:
                self.engine = self.engine_factory()
                self.sandbox_engine = self.engine_factory()
                raw_json = self.poe_api_client.fetch_character_raw(self.character_name)
                imp_res = self.engine.call("import_character", json=raw_json)
                self.ggg_payload = _as_payload(raw_json)
                self.xml = imp_res.get("xml")
                self.class_name = imp_res.get("className")
                self.level = imp_res.get("level")

                # Query each production-enabled core slot once while the imported build is hot.
                for slot in POB2_PRODUCTION_SLOTS:
                    equipped = self.engine.call("get_equipped", slot=slot)
                    if equipped:
                        self.equipped_items[slot] = equipped

                self._refresh_main_group()
                self.defenses_before = self.engine.call("get_defenses")
                self.stats_before = self.engine.call("calc_stats")
                self.is_available = True
                self.is_healthy = True
                self.unhealthy_reason = None
                self.last_synced_at = time.monotonic()
                return True
            except Exception as exc:
                self.is_available = False
                self.unavailable_reason = f"Initialization error: {exc}"
                self.is_healthy = False
                self.unhealthy_reason = f"Initialization error: {exc}"
                self.close()
                return False

        # Live environment initialization
        if not self.backend_path:
            self.is_available = False
            self.unavailable_reason = (
                "PoB2 backend directory not found. Please set POB2_MCP_PATH or ensure "
                "path-of-building-2-mcp is a sibling directory."
            )
            return False

        if not is_docker_daemon_running():
            self.is_available = False
            self.unavailable_reason = "Docker daemon is not running (zero-backend fallback active)"
            return False

        modules = load_pob_mcp_modules(self.backend_path)
        if modules is None:
            self.is_available = False
            self.unavailable_reason = "Failed to import pob_mcp modules"
            return False
        poe_api, poe_oauth = modules
        try:
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
        if not is_docker_daemon_running():
            self.is_available = False
            self.unavailable_reason = "Docker daemon is not running (zero-backend fallback active)"
            return False

        try:
            self.engine = PobEngine()
            self.engine.start()
            self.sandbox_engine = PobEngine()
            self.sandbox_engine.start()
        except Exception as exc:
            self.is_available = False
            self.unavailable_reason = f"Failed to start PoB2 Docker engine: {exc}"
            self.close()
            return False

        # Import character and setup initial baseline
        try:
            imp_res = self.engine.call("import_character", json=raw_json)
            self.ggg_payload = _as_payload(raw_json)
            self.xml = imp_res.get("xml")
            self.class_name = imp_res.get("className")
            self.level = imp_res.get("level")

            for slot in POB2_PRODUCTION_SLOTS:
                equipped = self.engine.call("get_equipped", slot=slot)
                if equipped:
                    self.equipped_items[slot] = equipped

            self._refresh_main_group()
            self.defenses_before = self.engine.call("get_defenses")
            self.stats_before = self.engine.call("calc_stats")
            self.is_available = True
            self.is_healthy = True
            self.unhealthy_reason = None
            self.last_synced_at = time.monotonic()
            return True
        except Exception as exc:
            self.is_available = False
            self.unavailable_reason = f"Failed to import character into PoB2: {exc}"
            self.is_healthy = False
            self.unhealthy_reason = f"Failed to import character into PoB2: {exc}"
            self.close()
            return False

    def _recover_session(self) -> bool:
        """Attempt a single recovery of the sandbox engine process.

        Must be called while holding self._engine_lock.
        """
        if self.sandbox_engine is None or not self.xml:
            return False
        try:
            logger = logging.getLogger(__name__)
            logger.info("Attempting auto-recovery for unhealthy PoB2 session (%s)...", self.character_name)
            if hasattr(self.sandbox_engine, "restart"):
                self.sandbox_engine.restart()
            elif hasattr(self.sandbox_engine, "ensure_alive"):
                self.sandbox_engine.ensure_alive()
            elif hasattr(self.sandbox_engine, "start"):
                self.sandbox_engine.start()

            self.sandbox_engine.call("import_build", xml=self.xml)
            primary_group = self.get_primary_socket_group()
            if primary_group:
                try:
                    self.sandbox_engine.call("set_main_skill", group=primary_group)
                except Exception:
                    pass
            self.defenses_before = self.sandbox_engine.call("get_defenses")
            self.stats_before = self.sandbox_engine.call("calc_stats")
            self.is_healthy = True
            self.unhealthy_reason = None
            logger.info("PoB2 session (%s) successfully recovered.", self.character_name)
            return True
        except Exception as exc:
            self.is_healthy = False
            self.unhealthy_reason = f"Recovery failed: {exc}"
            logging.getLogger(__name__).warning("PoB2 session (%s) recovery failed: %s", self.character_name, exc)
            return False

    def _refresh_main_group(self) -> None:
        """Lock the baseline engine on its highest-DPS socket group.

        GGG imports always set mainSocketGroup = 1 (often a 0-DPS buff), so every enabled
        group with an active skill is tried (mainDPS = FullDPS or CombinedDPS); ties keep
        PoB's own main group.
        """
        try:
            skills = self.engine.call("list_skills")
            pob_main = skills.get("mainSocketGroup")
            self.skill_groups = [
                g["index"] for g in skills.get("groups") or [] if g.get("enabled") and g.get("activeSkill")
            ]
            best, best_dps = pob_main, float("-inf")
            for idx in self.skill_groups:
                dps = _main_dps(self.engine, idx)
                if dps > best_dps or (dps == best_dps and idx == pob_main):
                    best, best_dps = idx, dps
            self.main_group = int(best) if best else None
            if self.main_group is not None:
                self.engine.call("set_main_skill", group=self.main_group)
        except Exception as exc:
            logging.getLogger(__name__).warning("Could not read PoB2 main socket group: %s", exc)
            self.main_group = None
            self.skill_groups = []

    def submit_candidate(
        self,
        candidate_raw: str,
        candidate_name: str = "",
        slot: str = "Helmet",
        source: str = "manual",
    ) -> int:
        """Register a new candidate with a monotonically increasing ID.

        Staleness is tracked per ``source`` so a manual compare is not
        superseded by an automatic clipboard watcher candidate (and vice versa).
        Synchronized via `_state_lock` without blocking on `_engine_lock`.
        """
        with self._state_lock:
            self._latest_candidate_id += 1
            self._latest_by_source[source] = self._latest_candidate_id
            return self._latest_candidate_id

    def is_stale(self, candidate_id: int, source: str = "manual") -> bool:
        """Check if a candidate ID is superseded by a newer candidate of the same source.

        Synchronized via `_state_lock` without blocking on `_engine_lock`.
        """
        with self._state_lock:
            return candidate_id < self._latest_by_source.get(source, 0)

    def _fetch_equipped(self, slot: str) -> dict[str, Any] | None:
        """Like get_equipped_item but lets engine errors propagate."""
        canonical_slot = normalize_and_validate_pob_slot(slot)
        if canonical_slot in self.equipped_items:
            return self.equipped_items[canonical_slot]
        if self.is_available and self.engine is not None:
            item = self.engine.call("get_equipped", slot=canonical_slot)
            if item:
                self.equipped_items[canonical_slot] = item
                return item
        return None

    def get_equipped_item(self, slot: str) -> dict[str, Any] | None:
        """Get equipped item dictionary for canonical slot."""
        try:
            return self._fetch_equipped(slot)
        except Exception:
            logger.warning("PoB2 get_equipped failed for %s", slot, exc_info=True)
            return None

    def equip_item(self, slot: str | SlotType, raw_item: str) -> bool:
        """Equip an item directly into the active PoB2 baseline build.

        Mutates the baseline XML, updates equipped_items, and recalculates
        defenses_before and stats_before so subsequent simulations compare
        against the freshly equipped item.
        """
        canonical_slot = normalize_and_validate_pob_slot(slot)
        if not self.is_available or self.engine is None or not self.xml:
            return False

        with self._engine_lock:
            try:
                # 1. Restore current baseline XML
                self.engine.call("import_build", xml=self.xml)
                # 2. Equip new item
                self.engine.call("equip_item", slot=canonical_slot, raw=raw_item)
                # 3. Export new baseline XML
                export_res = self.engine.call("export_xml")
                if not export_res or not export_res.get("xml"):
                    return False
                self.xml = export_res["xml"]
                # 4. Refresh equipped_items, socket groups (a skill-granting item reorders them) and baseline defense/stats
                self.equipped_items[canonical_slot] = self.engine.call("get_equipped", slot=canonical_slot)
                self._refresh_main_group()
                self.defenses_before = self.engine.call("get_defenses")
                self.stats_before = self.engine.call("calc_stats")
                return True
            except Exception as exc:
                logging.getLogger(__name__).warning("Failed to equip item in PoB2 session: %s", exc)
                return False

    def sync_character(self, raw_json: str | dict | None = None) -> bool:
        """Re-import character from GGG API or raw JSON and refresh all baseline caches."""
        if not self.is_available or self.engine is None:
            return False

        with self._engine_lock:
            try:
                if raw_json is None:
                    if self.poe_api_client is not None:
                        raw_json = self.poe_api_client.fetch_character_raw(self.character_name)
                    else:
                        from pob_mcp import poe_api
                        raw_json = poe_api.fetch_character_raw(self.character_name)

                imp_res = self.engine.call("import_character", json=raw_json)
                self.ggg_payload = _as_payload(raw_json)
                self.xml = imp_res.get("xml")
                self.class_name = imp_res.get("className")
                self.level = imp_res.get("level")

                for slot in POB2_PRODUCTION_SLOTS:
                    equipped = self.engine.call("get_equipped", slot=slot)
                    if equipped:
                        self.equipped_items[slot] = equipped

                if self.resist_penalty is not None and self.xml:  # a fresh import drops the act penalty
                    self.xml = _set_resist_penalty_in_xml(self.xml, self.resist_penalty)
                    self.engine.call("import_build", xml=self.xml)
                self._refresh_main_group()
                self.defenses_before = self.engine.call("get_defenses")
                self.stats_before = self.engine.call("calc_stats")
                self.last_synced_at = time.monotonic()
                return True
            except Exception as exc:
                logging.getLogger(__name__).warning("Failed to sync character in PoB2 session: %s", exc)
                return False

    def apply_zone(self, zone: str | None, level: int | None = None) -> bool:
        """Set the baseline's elemental resistance penalty to the act of ``zone``; True when it changed.

        An unknown zone (hideout, no log yet) keeps the last penalty; with none set yet, ``level`` picks the act.
        """
        penalty = resist_penalty_for_zone(zone)
        if penalty is None and self.resist_penalty is None:
            penalty = resist_penalty_for_act(act_for_level(level))
        if penalty is None or penalty == self.resist_penalty or not self.is_available or self.engine is None or not self.xml:
            return False
        with self._engine_lock:
            try:
                xml = _set_resist_penalty_in_xml(self.xml, penalty)
                self.engine.call("import_build", xml=xml)
                self.xml = xml
                self._refresh_main_group()
                self.defenses_before = self.engine.call("get_defenses")
                self.stats_before = self.engine.call("calc_stats")
            except Exception as exc:
                logging.getLogger(__name__).warning("Failed to apply resistance penalty for %r: %s", zone, exc)
                return False
            self.resist_penalty = penalty
            return True

    def needs_refresh(
        self,
        level: int | None,
        zone: str | None,
        max_age_s: float = 600.0,
        now: float | None = None,
        min_interval_s: float = 60.0,
    ) -> bool:
        """True when the character leveled up, changed zone, or the last sync is stale.

        Side-effect free (except recording the very first zone) and rate-limited to one
        attempt per ``min_interval_s``; call ``mark_refresh_started`` when a refresh begins.
        """
        now = time.monotonic() if now is None else now
        if self._last_zone is None and zone is not None:
            self._last_zone = zone
        if now - self.last_refresh_attempt_at < min_interval_s:
            return False
        known = [v for v in (self.level, self._handed_level) if v is not None]
        leveled = level is not None and bool(known) and level > max(known)
        zone_changed = zone is not None and self._last_zone is not None and zone != self._last_zone
        return leveled or zone_changed or (now - self.last_synced_at) > max_age_s

    def mark_refresh_started(self, level: int | None, zone: str | None, now: float | None = None) -> None:
        """Record a refresh attempt so its triggers (level, zone) are consumed exactly once."""
        self.last_refresh_attempt_at = time.monotonic() if now is None else now
        if level is not None:
            self._handed_level = level if self._handed_level is None else max(self._handed_level, level)
        if zone is not None:
            self._last_zone = zone

    def get_current_item_name(self, slot: str) -> str | None:
        """Get the current equipped item name for a given slot."""
        item = self.get_equipped_item(slot)
        if item and item.get("equipped"):
            return item.get("name")
        return None

    def is_slot_empty(self, slot: str) -> bool:
        """Return True if the specified canonical slot is empty in the loaded PoB2 build."""
        item = self._fetch_equipped(slot)  # engine errors propagate so callers can fall back
        if not item:
            return True
        return not item.get("equipped", False)

    def find_socket_group_for_skill(self, skill_context: str | None) -> int | None:
        """Find the 1-based socket group index in PoB2 corresponding to skill_context."""
        if not skill_context or not self.engine:
            return None
        try:
            skills = self.engine.call("list_skills")
            groups = skills.get("groups", [])
            target = skill_context.lower()

            # 1. Exact or substring match on activeSkill
            for g in groups:
                active = (g.get("activeSkill") or "").lower()
                if active and (target in active or active in target):
                    return g.get("index")

            # 2. Match gem name in gemList
            for g in groups:
                for gem in g.get("gems", []):
                    name = (gem.get("name") or "").lower()
                    if name and (target in name or target.replace(" ", "") in name.replace(" ", "")):
                        return g.get("index")

            # 3. Handle CROSSBOW_LEVELING alias
            if "crossbow" in target or "leveling" in target:
                for candidate_skill in ("explosive grenade", "crossbow shot", "gas grenade", "fragmentation rounds"):
                    for g in groups:
                        active = (g.get("activeSkill") or "").lower()
                        if candidate_skill in active:
                            return g.get("index")
        except Exception:
            return None
        return None

    def get_primary_socket_group(self, skill_context: str | None = None) -> int | None:
        """Socket group for ``skill_context`` if given and found, else PoB's own main group."""
        if skill_context and self.engine:
            idx = self.find_socket_group_for_skill(skill_context)
            if idx:
                return idx
        return self.main_group

    def _build_delta(
        self,
        canonical_slot: str,
        candidate_id: int,
        candidate_name: str,
        def_after: dict[str, Any],
        stats_after: dict[str, Any],
        def_before: dict[str, Any] | None = None,
        stats_before: dict[str, Any] | None = None,
    ) -> PobEquipmentDelta:
        """Compute delta between baseline stats and post-equip stats for a slot."""
        if def_before is None:
            def_before = self.defenses_before or {}
        if stats_before is None:
            stats_before = self.stats_before or {}

        required_defense_keys = {"Life", "Armour", "Evasion", "EnergyShield", "TotalEHP"}
        required_stat_defense_keys = {
            "FireResist", "ColdResist", "LightningResist", "ChaosResist"
        }
        missing_metrics = sorted(
            key for key in required_defense_keys if key not in def_before or key not in def_after
        )
        defense_before = stats_before.get("defense")
        defense_after = stats_after.get("defense")
        offense_before = stats_before.get("offense")
        offense_after = stats_after.get("offense")
        if not isinstance(defense_before, dict) or not isinstance(defense_after, dict):
            missing_metrics.append("defense")
        else:
            missing_metrics.extend(
                f"defense.{key}"
                for key in sorted(required_stat_defense_keys)
                if key not in defense_before or key not in defense_after
            )
        if not isinstance(offense_before, dict) or not isinstance(offense_after, dict):
            missing_metrics.append("offense")
        elif "CombinedDPS" not in offense_before or "CombinedDPS" not in offense_after:
            missing_metrics.append("offense.CombinedDPS")
        if missing_metrics:
            raise ValueError(f"Missing PoB2 metrics: {', '.join(sorted(set(missing_metrics)))}")

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

        def _off(key: str) -> tuple[float, float]:
            return float(off_before.get(key) or 0.0), float(off_after.get(key) or 0.0)

        def _pct(key: str) -> float:
            b, a = _off(key)
            return round((a - b) / b * 100, 1) if b else 0.0

        crit_b, crit_a = _off("CritChance")
        multi_b, multi_a = _off("CritMultiplier")  # PoB multiplier (2.0 = +100% Critical Damage Bonus)
        mana_delta = int((def_after.get("Mana") or 0) - (def_before.get("Mana") or 0))

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
            mana_delta=mana_delta,
            crit_chance_delta=round(crit_a - crit_b, 1),
            crit_bonus_delta=round((multi_a - multi_b) * 100, 1),
            average_hit_pct=_pct("AverageHit"),
            speed_pct=_pct("Speed"),
            life_before=life_before,
            life_after=life_after,
            ehp_before=ehp_before,
            ehp_after=ehp_after,
            dps_before=dps_before,
            dps_after=dps_after,
            res_before={k: float(def_stats_before.get(v) or 0) for k, v in _RES_KEYS.items()},
            res_after={k: float(def_stats_after.get(v) or 0) for k, v in _RES_KEYS.items()},
        )

    def measure(
        self,
        slot: str | SlotType,
        raw: str,
        candidate_id: int,
        *,
        source: str = "manual",
        clear_slots: tuple[str, ...] = (),
        candidate_name: str = "",
        main_skill: str | None = None,
        base_xml: str | None = None,
    ) -> PobEquipmentDelta | None:
        """Measure one candidate in one slot against its own context-specific baseline.

        Activates the weapon set the slot belongs to and locks one skill before both readings:
        for weapon slots the group whose DPS the candidate changes most, otherwise (or when
        no group changes) the guide stage's main skill when it matches a socket group, else
        the baseline's highest-DPS group. Applies ``clear_slots`` to the "after" build only
        and always restores the baseline XML. Returns None if stale, unavailable or on engine failure.
        """
        canonical_slot = normalize_and_validate_pob_slot(slot)
        if not self.is_available or self.sandbox_engine is None or not self.xml:
            return None
        if self.is_stale(candidate_id, source):
            return None

        log = logging.getLogger(__name__)
        with self._engine_lock:
            if self.is_stale(candidate_id, source):
                return None
            if not self.is_healthy and not self._recover_session():
                return None

            engine = self.sandbox_engine
            group = (self.find_socket_group_for_skill(main_skill) if main_skill else None) or self.main_group
            locked: str | None = None  # skill name: equipping an item that grants a skill reorders the groups

            def lock_skill() -> None:
                index = _skill_index(engine).get(locked) if locked else None
                if base_xml is None and index is not None:
                    engine.call("set_main_skill", group=index)

            try:
                base_to_use = base_xml if base_xml is not None else self.xml
                xml_set = _set_weapon_set_in_xml(base_to_use, 2 if canonical_slot.endswith("Swap") else 1)
                engine.call("import_build", xml=xml_set)
                names = {i: n for n, i in _skill_index(engine).items()}
                locked = names.get(group)
                if base_xml is None and canonical_slot.startswith("Weapon") and self.skill_groups:
                    # A weapon often feeds only its own skill (BOMSHAK: swap crossbow -> Oil Grenade), so when
                    # the weapon leaves `locked` untouched, lock the skill whose DPS the swap changes most.
                    # ponytail: 2 recalcs per group per weapon compare; cache per slot if it gets slow
                    skills = [names[g] for g in self.skill_groups if g in names]
                    dps_before = {n: _main_dps(engine, i) for n, i in _skill_index(engine).items() if n in skills}
                    if clear_slots:
                        engine.call("import_build", xml=_clear_slots_in_xml(xml_set, clear_slots))
                    engine.call("equip_item", slot=canonical_slot, raw=raw)
                    after = _skill_index(engine)
                    change = {
                        n: abs((_main_dps(engine, after[n]) if n in after else 0.0) - dps_before.get(n, 0.0))
                        for n in skills
                    }
                    if skills and change.get(locked, 0.0) == 0:
                        best = max(skills, key=lambda n: (change[n], n == locked))
                        if change[best] > 0:
                            locked = best
                    engine.call("import_build", xml=xml_set)
                lock_skill()
                def_before = engine.call("get_defenses")
                stats_before = engine.call("calc_stats")

                if clear_slots:
                    engine.call("import_build", xml=_clear_slots_in_xml(xml_set, clear_slots))
                    lock_skill()
                engine.call("equip_item", slot=canonical_slot, raw=raw)
                lock_skill()
                def_after = engine.call("get_defenses")
                stats_after = engine.call("calc_stats")

                if self.is_stale(candidate_id, source):
                    return None
                return self._build_delta(
                    canonical_slot, candidate_id, candidate_name, def_after, stats_after,
                    def_before=def_before, stats_before=stats_before,
                )
            except EngineError as exc:
                log.warning("PoB2 engine error for slot %s: %s", canonical_slot, exc)
                if base_xml is None:
                    self.is_healthy = False
                    self.unhealthy_reason = f"Engine error: {exc}"
                return None
            except Exception as exc:
                log.warning("PoB2 measurement failed for slot %s: %s", canonical_slot, exc)
                if "EngineError" in type(exc).__name__:
                    if base_xml is None:
                        self.is_healthy = False
                        self.unhealthy_reason = f"Engine error: {exc}"
                return None
            finally:
                try:
                    engine.call("import_build", xml=self.xml)
                except Exception as exc:
                    log.warning("Failed to restore baseline in PoB2 sandbox: %s", exc)
                    self.is_healthy = False
                    self.unhealthy_reason = f"Baseline restore failed: {exc}"

    def close(self) -> None:
        """Clean up both PoB engines (baseline + sandbox)."""
        with self._engine_lock:
            if self.sandbox_engine is not None and hasattr(self.sandbox_engine, "close"):
                try:
                    self.sandbox_engine.close()
                except Exception:
                    logger.warning("Failed to close PoB2 sandbox engine", exc_info=True)
                self.sandbox_engine = None
            if self.engine is not None and hasattr(self.engine, "close"):
                try:
                    self.engine.close()
                except Exception:
                    logger.warning("Failed to close PoB2 engine", exc_info=True)
                self.engine = None
            self.is_available = False
