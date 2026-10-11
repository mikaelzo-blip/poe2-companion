"""Web API endpoints for PoE2 Companion Dashboard local server."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import time
from pathlib import Path
from typing import Any

from companion.builds.store import get_assignment
from companion.equipment.clipboard import get_clipboard_text
from companion.equipment.current_item import character_level_and_zone, get_current_item_info, get_current_raw
from companion.equipment.evaluation import EvaluationResult, evaluate
from companion.equipment.parser import parse_item_text
from companion.equipment.pob2_equipment_advisor import load_pob_mcp_modules
from companion.equipment.slot_resolver import UI_SLOT_KEYS
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore

logger = logging.getLogger(__name__)


def resolve_char_id(char_id: str | None, runtime_dir: Path) -> str:
    """Match a character ID case-insensitively against runtime/characters/*.json (default BOMSHAK)."""
    raw = str(char_id or "").strip() or "BOMSHAK"
    chars_dir = runtime_dir / "characters"
    if chars_dir.is_dir():
        for f in chars_dir.glob("*.json"):
            if f.stem.lower() == raw.lower():
                return f.stem
    return raw


def _stamp_evaluated(res: dict[str, Any]) -> dict[str, Any]:
    if res.get("success"):
        res.setdefault("evaluated_at", datetime.now(timezone.utc).isoformat())
    return res


def flatten_result(r: EvaluationResult) -> dict[str, Any]:
    """Flatten an EvaluationResult into the response shape the dashboard UI reads."""
    chosen = next((s for s in r.per_slot if s.slot == r.slot), None)
    delta = chosen.delta if chosen else None
    dps_pct = chosen.dps_pct if chosen else 0.0
    ehp_pct = chosen.ehp_pct if chosen else 0.0
    slot_empty = chosen.is_empty if chosen else False
    auto_equip_ok = r.verdict == "EQUIP_NOW" and slot_empty
    tactical = r.tactical_advice or {}
    reason = (r.reasons[0] if r.reasons else None) or tactical.get("tactical_headline") or r.verdict
    lines = [f"{r.verdict} - {r.item_name} ({r.slot})", *r.reasons]
    lines += [f"+ {g}" for g in r.gains] + [f"- {t}" for t in r.trade_offs]
    return {
        "success": True,
        "engine": r.engine,
        "engine_reason": r.engine_reason,
        "item_name": r.item_name,
        "base_type": r.base_type,
        "verdict": r.verdict,
        "reason": reason,
        "gains": r.gains,
        "trade_offs": r.trade_offs,
        "formatted_report": "\n".join(lines),
        "tactical_advice": r.tactical_advice,
        "current_item_name": r.current_item_name,
        "current_item_base_type": r.current_item_base_type,
        "is_weapon": r.slot.startswith("Weapon"),
        "dps_delta": delta.dps_delta if delta else 0,
        "life_delta": delta.life_delta if delta else 0,
        "dps_pct": dps_pct,
        "ehp_pct": ehp_pct,
        "slot_empty": slot_empty,
        "auto_equip_ok": auto_equip_ok,
        "slot": UI_SLOT_KEYS[r.slot],
        "pob_slot": r.slot,
        "recommended_slot": r.slot,
        "slot_reason": r.slot_reason,
        "dims": r.dims,
        "guide": r.guide.model_dump() if r.guide else None,
        "safety": r.safety,
        "per_slot": [s.model_dump(mode="json", exclude={"delta"}) for s in r.per_slot],
    }


def evaluate_item_payload(
    payload: dict[str, Any],
    runtime_dir: Path,
    pob_session: Any | None = None,
) -> dict[str, Any]:
    """Evaluate submitted item text through the guide-aware pipeline. Legacy guide/stage fields are ignored."""
    raw_text = payload.get("raw_text", "").strip()
    if not raw_text:
        return {"error": "Item raw text is empty."}
    char_id = resolve_char_id(payload.get("character_id"), runtime_dir)
    try:
        r = evaluate(
            raw_text, char_id, runtime_dir=runtime_dir, pob_session=pob_session,
            source=payload.get("source", "manual"), locked_slot=payload.get("slot") or None, zone=payload.get("zone"),
        )
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        logger.exception("Evaluation failed for %r", char_id)
        return {"error": f"Evaluation error: {exc}"}
    return _stamp_evaluated(flatten_result(r))


_LAST_SEEN_CLIPBOARD = ""

def check_auto_clipboard(
    runtime_dir: Path,
    char_id: str,
    pob_session: Any | None = None,
    zone: str | None = None,
    pob_session_resolver: Any | None = None,
) -> dict[str, Any]:
    """Poll OS clipboard automatically and evaluate if a new PoE2 item is detected."""
    global _LAST_SEEN_CLIPBOARD
    current_text = get_clipboard_text().strip()

    char_id = resolve_char_id(char_id, runtime_dir)
    current_key = f"{current_text}::{char_id}::{get_assignment(runtime_dir, char_id)}::{zone}"
    if not current_text or _LAST_SEEN_CLIPBOARD in (current_text, current_key):
        return {"has_new_item": False}

    # Verify if it looks like a PoE item
    if "Rarity:" not in current_text and "Item Class:" not in current_text:
        return {"has_new_item": False}

    _LAST_SEEN_CLIPBOARD = current_key

    if pob_session is None and callable(pob_session_resolver):
        try:
            pob_session = pob_session_resolver()
        except Exception:
            logger.warning("PoB2 session resolver failed; evaluating without PoB2", exc_info=True)
            pob_session = None

    result = evaluate_item_payload(
        {"raw_text": current_text, "character_id": char_id, "zone": zone, "source": "auto"},
        runtime_dir=runtime_dir,
        pob_session=pob_session,
    )
    result["has_new_item"] = True
    result["raw_text"] = current_text
    return result


def update_loadout_item_payload(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    from companion.equipment.loadout_cli import character_runtime_lock
    with character_runtime_lock(payload.get("character_id", "BOMSHAK")):
        return _update_loadout_item_payload_locked(payload, runtime_dir)


def _update_loadout_item_payload_locked(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    """Equip or update an item in character loadout from web UI."""
    raw_text = payload.get("raw_text", "").strip()
    if not raw_text:
        return {"error": "Item text cannot be empty."}

    char_id = payload.get("character_id", "BOMSHAK")
    slot_name = payload.get("slot")
    weapon_set_name = payload.get("weapon_set")

    try:
        candidate = parse_item_text(raw_text)
    except Exception as exc:
        return {"error": f"Failed to parse item: {exc}"}

    # Resolve specific slot name
    target_slot = slot_name
    if not target_slot:
        if candidate.slot:
            target_slot = candidate.slot.value
        elif "crossbow" in candidate.base_type.lower() or "staff" in candidate.base_type.lower() or "bow" in candidate.base_type.lower():
            target_slot = "main_hand"
        elif "ring" in candidate.base_type.lower():
            target_slot = "ring1"
        else:
            return {"error": "Could not determine equipment slot for item."}

    # Map generic/prefixed names sent from UI
    norm_slot = target_slot.lower().strip()
    if norm_slot.startswith("set2_"):
        target_slot = norm_slot[5:]
        weapon_set_name = weapon_set_name or "weapon_set_2"
    elif norm_slot.startswith("swap_"):
        target_slot = norm_slot[5:]
        weapon_set_name = weapon_set_name or "weapon_set_2"
    elif norm_slot in ("ring", "ring_1", "ring1"):
        target_slot = "ring1"
    elif norm_slot in ("ring_2", "ring2"):
        target_slot = "ring2"
    elif norm_slot == "weapon":
        target_slot = "main_hand"

    from companion.equipment.loadout_cli import run_loadout_set_item
    try:
        updated_loadout = run_loadout_set_item(
            runtime_dir=runtime_dir,
            character_id=char_id,
            slot_name=target_slot,
            item_text=raw_text,
            weapon_set_name=weapon_set_name,
        )
        return {
            "success": True,
            "message": f"Berhasil memasang {candidate.name or candidate.base_type} ke slot {target_slot.upper()}.",
            "slot": target_slot,
            "item_name": candidate.name or candidate.base_type,
            "revision": updated_loadout.revision,
            "character_id": char_id,
        }
    except Exception as exc:
        return {"error": f"Gagal update loadout: {exc}"}


def import_character_payload(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    from companion.equipment.loadout_cli import character_runtime_lock
    with character_runtime_lock(payload.get("character_id", "BOMSHAK")):
        return _import_character_payload_locked(payload, runtime_dir)


def _import_character_payload_locked(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    """Import full character equipment JSON (from GGG get-items or export)."""
    char_id = payload.get("character_id", "BOMSHAK")
    raw_payload = payload.get("character_data") or payload
    if not isinstance(raw_payload, dict):
        return {"error": "Invalid character JSON data."}
    overwrite = payload.get("overwrite", True)

    from companion.equipment.api_adapter import GGGCharacterAPIAdapter
    from companion.equipment.loadout_cli import load_loadout, save_loadout
    from companion.equipment.baseline import BaselineSource
    from companion.equipment.baseline_cli import load_baseline, save_baseline

    current_loadout = load_loadout(runtime_dir, char_id)
    current_baseline = load_baseline(runtime_dir, char_id)
    loadout, baseline, warnings = GGGCharacterAPIAdapter.parse_character_payload(
        raw_payload=raw_payload,
        character_id=char_id,
        current_loadout=current_loadout,
        overwrite_conflicts=overwrite,
    )
    if loadout is None:
        return {"error": "; ".join(warnings) if warnings else "Gagal membaca item karakter dari JSON."}

    save_loadout(runtime_dir, loadout)
    if baseline is not None:
        if current_baseline is not None:
            same_gear = (
                current_loadout is not None and current_loadout.is_finalized
                and current_loadout.compute_fingerprint() == loadout.compute_fingerprint()
            )
            if same_gear:
                # Same gear: keep the previous anchor so the following apply does not stale every fact.
                baseline.anchored_loadout_fingerprint = current_baseline.anchored_loadout_fingerprint
            for attr_name in (
                "life", "armour", "evasion", "energy_shield", "mana", "spirit", "deflection",
                "raw_fire_res", "effective_fire_res", "max_fire_res", "fire_overcap_buffer",
                "raw_cold_res", "effective_cold_res", "max_cold_res", "cold_overcap_buffer",
                "raw_lightning_res", "effective_lightning_res", "max_lightning_res", "lightning_overcap_buffer",
                "raw_chaos_res", "effective_chaos_res", "max_chaos_res", "chaos_overcap_buffer",
                "strength", "dexterity", "intelligence", "movement_speed",
            ):
                old = getattr(current_baseline, attr_name, None)
                new = getattr(baseline, attr_name, None)
                if old is not None and getattr(old, "source", None) == BaselineSource.MANUAL_USER_INPUT:
                    setattr(baseline, attr_name, old if same_gear else old.mark_stale())
                elif new is not None and getattr(new, "is_known", False):
                    continue
                elif old is not None and getattr(old, "value", None) is not None:
                    setattr(baseline, attr_name, old.mark_stale())
        save_baseline(runtime_dir, baseline)

    # Persist or update CharacterState with name, class, level
    try:
        from companion.state.schema import CharacterState, ProvenancedField
        from companion.state.store import CharacterStateStore

        char_info = raw_payload.get("character") or {}
        char_level = char_info.get("level") or raw_payload.get("level")
        char_class = char_info.get("class") or raw_payload.get("class") or "Mercenary"
        char_name = char_info.get("name") or char_id

        store = CharacterStateStore(runtime_dir=runtime_dir)
        try:
            existing_state = store.load_character(char_id)
        except Exception:
            existing_state = None

        if existing_state:
            existing_state.character_name = char_name
            existing_state.character_class = char_class
            if char_level is not None:
                existing_state.level = ProvenancedField[int].create(int(char_level), source="OFFICIAL_API_POLL")
            store.save_character(existing_state)
        else:
            lvl_val = int(char_level) if char_level is not None else 1
            new_state = CharacterState(
                character_id=char_id,
                character_name=char_name,
                character_class=char_class,
                level=ProvenancedField[int].create(lvl_val, source="OFFICIAL_API_POLL"),
            )
            store.save_character(new_state)
    except Exception:
        pass

    return {
        "success": True,
        "character_id": char_id,
        "imported_slots": len(loadout.known_slots),
        "slots": [s.value if hasattr(s, "value") else str(s) for s in loadout.known_slots],
        "message": f"Berhasil mengimpor {len(loadout.known_slots)} slot perlengkapan untuk {char_id}!",
        "warnings": warnings,
    }


def update_character_stats_payload(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    from companion.equipment.loadout_cli import character_runtime_lock
    with character_runtime_lock(payload.get("character_id") or "BOMSHAK"):
        return _update_character_stats_payload_locked(payload, runtime_dir)


def _update_character_stats_payload_locked(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    """Update CharacterState and CharacterStatBaseline with live character stats from in-game / UI."""
    char_id = payload.get("character_id") or "BOMSHAK"

    from companion.state.schema import CharacterState, ProvenancedField
    from companion.state.store import CharacterStateStore
    from companion.equipment.fubgun_priorities import infer_stage_from_level

    store = CharacterStateStore(runtime_dir=runtime_dir)
    try:
        state = store.load_character(char_id)
    except Exception:
        state = CharacterState(
            character_id=char_id,
            character_name=payload.get("character_name") or char_id,
            character_class=payload.get("character_class") or "Mercenary",
            ascendancy=payload.get("ascendancy") or "Gemling Legionnaire",
        )

    if payload.get("character_name"):
        state.character_name = payload["character_name"]
    if payload.get("character_class"):
        state.character_class = payload["character_class"]
    if payload.get("ascendancy"):
        state.ascendancy = payload["ascendancy"]

    if payload.get("level") is not None:
        lvl_val = int(payload["level"])
        state.level = ProvenancedField[int].create(lvl_val, source="USER_IN_GAME_SYNC")
        stage_enum = infer_stage_from_level(lvl_val)
        display_map = {
            "LEVELING_1_14": "lvl 1-14",
            "LEVELING_15_32": "lvl 15-32",
            "LEVELING_33_51": "lvl 33-51",
            "SWAP_52": "lvl 52 Swap",
            "LEVELING_53_68": "lvl 53-68",
            "LEVEL_85": "lvl 85",
            "ENDGAME": "Endgame",
        }
        state.build_progression["active_stage"] = display_map.get(getattr(stage_enum, "value", str(stage_enum)), "lvl 33-51")


    # Attributes
    for attr in ("strength", "dexterity", "intelligence"):
        if payload.get(attr) is not None:
            val = int(payload[attr])
            state.attributes[attr] = ProvenancedField[int].create(val, source="USER_IN_GAME_SYNC")

    # Resources (mana, spirit)
    for res_key in ("mana", "spirit"):
        if payload.get(res_key) is not None:
            val = int(payload[res_key])
            state.resources[res_key] = ProvenancedField[int].create(val, source="USER_IN_GAME_SYNC")

    # Resistances
    for res in ("fire", "cold", "lightning", "chaos"):
        val = payload.get(f"{res}_res") if payload.get(f"{res}_res") is not None else payload.get(res)
        if val is not None:
            state.resistances[res] = ProvenancedField[int].create(int(val), source="USER_IN_GAME_SYNC")

    store.save_character(state)

    # 2. Update or create CharacterStatBaseline
    from companion.equipment.baseline import CharacterStatBaseline, CharacterFact, BaselineSource
    from companion.equipment.baseline_cli import load_baseline, save_baseline

    baseline = load_baseline(runtime_dir, char_id)
    if baseline is None:
        baseline = CharacterStatBaseline.create_empty(character_id=char_id, anchored_loadout_revision=1)

    # Update defensive stats
    if payload.get("life") is not None:
        baseline.life = CharacterFact[int].create(int(payload["life"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("armour") is not None:
        baseline.armour = CharacterFact[int].create(int(payload["armour"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("evasion") is not None:
        baseline.evasion = CharacterFact[int].create(int(payload["evasion"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("energy_shield") is not None:
        baseline.energy_shield = CharacterFact[int].create(int(payload["energy_shield"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("mana") is not None:
        baseline.mana = CharacterFact[int].create(int(payload["mana"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("spirit") is not None:
        baseline.spirit = CharacterFact[int].create(int(payload["spirit"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("deflection") is not None:
        baseline.deflection = CharacterFact[int].create(int(payload["deflection"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("movement_speed") is not None:
        baseline.movement_speed = CharacterFact[int].create(int(payload["movement_speed"]), source=BaselineSource.MANUAL_USER_INPUT)

    # Attributes on baseline
    if payload.get("strength") is not None:
        baseline.strength = CharacterFact[int].create(int(payload["strength"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("dexterity") is not None:
        baseline.dexterity = CharacterFact[int].create(int(payload["dexterity"]), source=BaselineSource.MANUAL_USER_INPUT)
    if payload.get("intelligence") is not None:
        baseline.intelligence = CharacterFact[int].create(int(payload["intelligence"]), source=BaselineSource.MANUAL_USER_INPUT)

    # Resistances on baseline
    for res in ("fire", "cold", "lightning", "chaos"):
        val = payload.get(f"{res}_res") if payload.get(f"{res}_res") is not None else payload.get(res)
        if val is not None:
            int_val = int(val)
            setattr(baseline, f"raw_{res}_res", CharacterFact[int].create(int_val, source=BaselineSource.MANUAL_USER_INPUT))
            setattr(baseline, f"effective_{res}_res", CharacterFact[int].create(int_val, source=BaselineSource.MANUAL_USER_INPUT))
            setattr(baseline, f"max_{res}_res", CharacterFact[int].create(75, source=BaselineSource.MANUAL_USER_INPUT))

    save_baseline(runtime_dir, baseline)

    return {
        "success": True,
        "character_id": char_id,
        "message": f"Stat karakter {char_id} berhasil diperbarui secara live!",
    }



_OAUTH_REQUIRED_MSG = "Login PoE belum aktif/kedaluwarsa. Jalankan login via PoB2 MCP (poe_login_start)."
_API_CHARS_TTL = 300.0
_API_CHARS_CACHE: dict[str, Any] = {}


def _list_api_characters(now: float | None = None) -> list[dict[str, Any]]:
    """Characters from the official GGG API via PoB2 MCP, cached for 300 s. [] on any failure."""
    now = time.monotonic() if now is None else now
    cached = _API_CHARS_CACHE.get("entry")
    if cached and now - cached[0] < _API_CHARS_TTL:
        return list(cached[1])
    modules = load_pob_mcp_modules()
    if modules is None:
        logger.warning("PoB2 MCP not found; cannot list GGG characters")
        return []
    poe_api, poe_oauth = modules
    try:
        if not poe_oauth.get_valid_token():
            logger.warning("No valid PoE OAuth token; cannot list GGG characters")
            return []
        chars = [
            {
                "name": c["name"],
                "level": c.get("level", 1),
                "class": c.get("class", "Unknown"),
                "league": c.get("league", "Standard"),
            }
            for c in poe_api.list_characters()
            if c.get("name")
        ]
    except Exception as exc:
        logger.warning("GGG list_characters failed: %s", exc)
        return []
    _API_CHARS_CACHE["entry"] = (now, chars)
    return list(chars)


def fetch_public_profile(account_name: str, character_id: str, runtime_dir: Path, overwrite: bool = True) -> dict[str, Any]:
    """Import a character through the official GGG API (PoB2 MCP). Returns an error dict on failure."""
    character_id = character_id.strip()
    modules = load_pob_mcp_modules()
    if modules is None:
        return {"error": "POB2_MCP_NOT_FOUND", "message": "Folder path-of-building-2-mcp tidak ditemukan. Set POB2_MCP_PATH."}
    poe_api, poe_oauth = modules
    try:
        token = poe_oauth.get_valid_token()
    except Exception as exc:
        logger.info("get_valid_token raised: %s", exc)
        token = None
    if not token:
        return {"error": "OAUTH_REQUIRED", "message": _OAUTH_REQUIRED_MSG}
    try:
        raw_data = poe_api.fetch_character_raw(character_id)
        parsed_data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
    except Exception as exc:
        logger.warning("GGG fetch_character_raw failed for %s: %s", character_id, exc)
        return {"error": "GGG_API_ERROR", "message": str(exc)}
    res = import_character_payload({"character_id": character_id, "character_data": parsed_data, "overwrite": overwrite}, runtime_dir)
    if res.get("success"):
        res["message"] = f"Berhasil menarik {res.get('imported_slots')} slot perlengkapan resmi untuk {character_id} dari GGG PoE2 API!"
    return res


def get_dashboard_status(
    runtime_dir: Path,
    char_id: str | None = None,
    pob_session: Any | None = None,
) -> dict[str, Any]:
    """Gather live runtime status, active character, current objective, baseline, loadout, and engine health."""
    if not char_id:
        active_file = runtime_dir / "active_character.json"
        if active_file.is_file():
            try:
                active_data = json.loads(active_file.read_text(encoding="utf-8"))
                if active_data.get("active_character_id"):
                    char_id = active_data["active_character_id"]
            except Exception:
                pass

    status_data: dict[str, Any] = {"game_process_running": False}
    char_data: dict[str, Any] = {}
    obj_data: dict[str, Any] = {}
    loadout_data: dict[str, Any] = {}
    baseline_data: dict[str, Any] = {}

    status_file = runtime_dir / "runtime_status.json"
    if status_file.is_file():
        try:
            status_data = json.loads(status_file.read_text(encoding="utf-8"))
            if not char_id and status_data.get("active_character_id"):
                char_id = status_data["active_character_id"]
        except Exception:
            pass

    if not char_id:
        char_id = "BOMSHAK"

    status_data["active_character_id"] = char_id

    # Gather PoB2 engine health status
    engine_status: dict[str, Any] = {
        "available": False,
        "healthy": False,
        "unhealthy_reason": None,
        "unavailable_reason": None,
    }
    target_pob = pob_session
    if target_pob is None and char_id:
        try:
            from companion.dashboard_server import _GLOBAL_POB_SESSIONS
            target_pob = _GLOBAL_POB_SESSIONS.get(char_id)
        except Exception:
            pass

    if target_pob is not None:
        engine_status["available"] = bool(getattr(target_pob, "is_available", False))
        engine_status["healthy"] = bool(getattr(target_pob, "is_healthy", False))
        engine_status["unhealthy_reason"] = getattr(target_pob, "unhealthy_reason", None)
        engine_status["unavailable_reason"] = getattr(target_pob, "unavailable_reason", None)

    status_data["engine_healthy"] = engine_status["healthy"]

    char_file = runtime_dir / "characters" / f"{char_id}.json"
    if char_file.is_file():
        try:
            char_data = json.loads(char_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    obj_file = runtime_dir / "CURRENT_OBJECTIVE.json"
    if obj_file.is_file():
        try:
            obj_data = json.loads(obj_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    from companion.equipment.loadout_cli import load_loadout
    loadout = load_loadout(runtime_dir, char_id)
    if loadout:
        loadout_data = loadout.model_dump()

    from companion.equipment.baseline_cli import load_baseline
    baseline = load_baseline(runtime_dir, char_id)
    if baseline:
        baseline_data = baseline.model_dump()

    return {
        "status": status_data,
        "character": char_data,
        "objective": obj_data,
        "loadout": loadout_data,
        "baseline": baseline_data,
        "active_character_id": char_id,
        "engine_status": engine_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_account_characters(
    account_name: str = "mikaelzo#5674",
    runtime_dir: Path | None = None,
) -> dict[str, Any]:
    """Discover available characters for an account from the GGG API and local runtime files."""
    if runtime_dir is None:
        runtime_dir = Path(__file__).resolve().parent.parent / "runtime"

    characters: list[dict[str, Any]] = list(_list_api_characters())
    source = "api" if characters else "local"
    seen_names = {c["name"] for c in characters}

    char_dir = runtime_dir / "characters"
    if char_dir.is_dir():
        for f in char_dir.glob("*.json"):
            try:
                c_data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                logger.warning("Skipping unreadable character file %s: %s", f, exc)
                continue
            if not isinstance(c_data, dict):
                logger.warning("Skipping non-object character file %s", f)
                continue
            c_name = c_data.get("character_name") or c_data.get("character_id") or f.stem
            if c_name in seen_names:
                continue  # API entry wins
            seen_names.add(c_name)
            lvl_obj = c_data.get("level", 1)
            lvl_val = lvl_obj.get("value", 1) if isinstance(lvl_obj, dict) else (lvl_obj if isinstance(lvl_obj, int) else 1)
            characters.append({
                "name": c_name,
                "level": lvl_val,
                "class": c_data.get("character_class", "Unknown"),
                "league": "Local",
            })

    active_char_id = "BOMSHAK"
    active_file = runtime_dir / "active_character.json"
    if active_file.is_file():
        try:
            a_data = json.loads(active_file.read_text(encoding="utf-8"))
            if a_data.get("active_character_id"):
                active_char_id = a_data["active_character_id"]
        except Exception:
            pass

    return {
        "account": account_name,
        "characters": characters,
        "active_character_id": active_char_id,
        "source": source,
    }


def select_character_payload(
    payload: dict[str, Any],
    runtime_dir: Path | None = None,
) -> dict[str, Any]:
    """Switch the active character across the companion suite."""
    char_id = payload.get("character_id", "").strip()
    if not char_id:
        return {"error": "character_id is required."}

    if runtime_dir is None:
        runtime_dir = Path("runtime")

    account_name = payload.get("account_name", "mikaelzo#5674")

    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_dir = runtime_dir / "characters"
    char_dir.mkdir(parents=True, exist_ok=True)
    char_file = char_dir / f"{char_id}.json"
    active_file = runtime_dir / "active_character.json"
    active_data = {
        "active_character_id": char_id,
        "file_path": str(char_file.resolve()),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    active_file.write_text(json.dumps(active_data, indent=2), encoding="utf-8")

    status_file = runtime_dir / "runtime_status.json"
    if status_file.is_file():
        try:
            s_data = json.loads(status_file.read_text(encoding="utf-8"))
            s_data["active_character_id"] = char_id
            status_file.write_text(json.dumps(s_data, indent=2), encoding="utf-8")
        except Exception:
            pass

    if not char_file.is_file():
        acc_info = get_account_characters(account_name=account_name, runtime_dir=runtime_dir)
        found_meta = next((c for c in acc_info.get("characters", []) if c["name"].lower() == char_id.lower()), None)
        c_class = found_meta["class"] if found_meta else "Mercenary"
        c_level = found_meta["level"] if found_meta else 1

        try:
            from companion.state.schema import CharacterState, ProvenancedField
            from companion.state.store import CharacterStateStore
            store = CharacterStateStore(runtime_dir=runtime_dir)
            new_state = CharacterState(
                character_id=char_id,
                character_name=char_id,
                character_class=c_class,
                level=ProvenancedField[int].create(int(c_level), source="OFFICIAL_API_POLL"),
            )
            store.save_character(new_state)
        except Exception:
            pass

        try:
            fetch_public_profile(account_name=account_name, character_id=char_id, runtime_dir=runtime_dir)
        except Exception:
            pass

    try:
        from companion.dashboard_server import invalidate_pob_session
        invalidate_pob_session(char_id)
    except Exception:
        pass

    return {
        "success": True,
        "active_character_id": char_id,
        "message": f"Karakter aktif berhasil diubah menjadi {char_id}!",
    }


def get_available_guides(runtime_dir: Path, character_id: str | None = None) -> dict[str, Any]:
    """List imported guides and the guide/stage assigned to ``character_id``."""
    from companion.builds.store import list_guides

    guide, override = get_assignment(runtime_dir, character_id) if character_id else (None, None)
    return {
        "guides": [
            {
                "slug": g.slug,
                "name": g.name,
                "source_url": g.source_url,
                "has_pob": g.has_pob,
                "stages": [
                    {"id": s.id, "title": s.title, "min_level": s.min_level,
                     "max_level": s.max_level, "auto": s.auto}
                    for s in g.stages
                ],
                "breaker_rules": [r.model_dump() for r in g.breaker_rules],
            }
            for g in list_guides(runtime_dir)
        ],
        "active": {"guide": guide, "stage_override": override},
    }


def import_guide_payload(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    """Import a guide from bookmarklet JSON, a pobb.in URL or a PoB2 share code."""
    from datetime import date

    from companion.builds import pob_code
    from companion.builds.mobalytics import parse_mobalytics_guide
    from companion.builds.known_rules import default_rules_for
    from companion.builds.store import load_guide, save_guide, set_breaker_rules

    text = str(payload.get("text") or "").strip()
    if not text:
        return {"error": "Teks guide kosong."}
    warnings: list[str] = []
    try:
        if text.startswith("{"):
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("JSON guide tidak valid atau terpotong.") from exc
            profile, code, warnings = parse_mobalytics_guide(data)
            xml = None
            if code:
                try:
                    xml = pob_code.decode_share_code(code)
                except ValueError as exc:
                    warnings.append(f"Kode PoB2 dilewati: {exc}")
                    profile = profile.model_copy(update={"has_pob": False})
        else:
            if text.startswith("https://pobb.in/"):
                try:
                    code = pob_code.fetch_pobb_code(text)
                except OSError as exc:
                    raise ValueError(f"Gagal mengambil dari pobb.in: {exc}") from exc
            else:
                code = text
            xml = pob_code.decode_share_code(code)
            profile = pob_code.parse_pob_xml(xml, f"PoB Guide {date.today().isoformat()}")
            base, n = profile.slug, 1
            while load_guide(runtime_dir, profile.slug) is not None:  # never overwrite another import
                n += 1
                profile = profile.model_copy(update={"slug": f"{base}-{n}"})
        replaced = load_guide(runtime_dir, profile.slug) is not None
        saved = save_guide(runtime_dir, profile, pob_xml=xml)
        if not saved.breaker_rules:
            defaults = default_rules_for(saved.source_url)
            if defaults:
                saved = set_breaker_rules(runtime_dir, saved.slug, defaults)
        if replaced:
            warnings.append(
                f"Guide '{saved.name}' yang sudah ada ditimpa (aturan breaker dipertahankan)")
    except ValueError as exc:
        return {"error": str(exc)}
    return {"success": True, "slug": saved.slug, "name": saved.name,
            "stages": len(saved.stages), "warnings": warnings}


def delete_guide_payload(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    from companion.builds.store import delete_guide

    if not delete_guide(runtime_dir, str(payload.get("slug") or "")):
        return {"error": "Guide tidak ditemukan."}
    return {"success": True}


def update_guide_rules_payload(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    from pydantic import ValidationError

    from companion.builds.guide import BreakerRule
    from companion.builds.store import set_breaker_rules

    try:
        rules = [BreakerRule.model_validate(r) for r in payload.get("rules") or []]
    except ValidationError as exc:
        err = exc.errors()[0]
        if err["loc"] and err["loc"][-1] == "pattern":
            return {"error": f"Pola regex tidak valid: {err['msg'].removeprefix('Value error, ')}"}
        return {"error": f"Aturan tidak valid: {err['msg']}"}
    try:
        set_breaker_rules(runtime_dir, str(payload.get("slug") or ""), rules)
    except (KeyError, ValueError):
        return {"error": "Guide tidak ditemukan."}
    return {"success": True}


def set_character_guide_payload(payload: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    from companion.builds.store import load_guide, set_assignment

    char_id, guide = payload.get("character_id"), payload.get("guide")
    override = payload.get("stage_override")
    if not char_id:
        return {"error": "character_id wajib diisi."}
    if guide is not None:
        profile = load_guide(runtime_dir, str(guide))
        if profile is None:
            return {"error": "Guide tidak ditemukan."}
        ids = {s.id for s in profile.stages}
        if override is not None and (not isinstance(override, str) or override not in ids):
            return {"error": "Tahap guide tidak dikenal."}
    elif override is not None:
        return {"error": "Tahap tidak bisa diatur tanpa guide."}
    set_assignment(runtime_dir, str(char_id), guide, override)
    return {"success": True}


