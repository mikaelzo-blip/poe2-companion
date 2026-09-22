"""Gear audit storage, persistence, and workflow orchestration."""

from __future__ import annotations

import json
from pathlib import Path

from companion.gear.schema import EquippedItem, GearAuditState, ItemSlot
from companion.gear.tooltip import verify_tooltip_stability
from companion.state.provenance import VerificationState
from companion.state.store import atomic_write_file


def _get_gear_file_path(runtime_dir: Path | str, character_id: str) -> Path:
    base = Path(runtime_dir) / "gear"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{character_id}_gear.json"


def load_gear_audit_state(runtime_dir: Path | str, character_id: str) -> GearAuditState:
    """Load persisted gear audit state for a character, or initialize empty."""
    gear_file = _get_gear_file_path(runtime_dir, character_id)
    if not gear_file.exists():
        return GearAuditState(character_id=character_id)

    try:
        data = json.loads(gear_file.read_text(encoding="utf-8"))
        # Parse slot keys into ItemSlot enums
        slots_dict = {}
        for k, v in data.get("slots", {}).items():
            slot_enum = ItemSlot(k)
            slots_dict[slot_enum] = EquippedItem.model_validate(v)
        return GearAuditState(
            character_id=data.get("character_id", character_id),
            slots=slots_dict,
            updated_at=data.get("updated_at"),
        )
    except Exception:
        return GearAuditState(character_id=character_id)


def save_gear_audit_state(runtime_dir: Path | str, state: GearAuditState) -> Path:
    """Persist gear audit state atomically to disk."""
    gear_file = _get_gear_file_path(runtime_dir, state.character_id)
    serialized = json.dumps(state.model_dump(), indent=2)
    atomic_write_file(gear_file, serialized.encode("utf-8"))
    return gear_file


def record_slot_audit(
    runtime_dir: Path | str,
    character_id: str,
    slot: ItemSlot,
    tooltip_captures: list[str],
) -> tuple[EquippedItem | None, VerificationState, GearAuditState]:
    """Verify captures, record verified slot, and persist state."""
    item, ver_state = verify_tooltip_stability(tooltip_captures, slot=slot)
    current_state = load_gear_audit_state(runtime_dir, character_id)

    if item is not None:
        updated_slots = dict(current_state.slots)
        updated_slots[slot] = item
        new_state = current_state.model_copy(update={"slots": updated_slots})
        save_gear_audit_state(runtime_dir, new_state)
        return item, ver_state, new_state

    return None, ver_state, current_state
