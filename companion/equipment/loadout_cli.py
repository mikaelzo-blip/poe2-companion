"""CLI handlers and storage operations for EquippedLoadout."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from companion.state.store import atomic_write_file
from companion.equipment.baseline import BaselineSource
from companion.equipment.parser import parse_item_text
from companion.equipment.loadout import (
    ALL_SHARED_SLOTS,
    ALL_WEAPON_SLOTS,
    EquippedLoadout,
)
from companion.equipment.schema import SlotType, WeaponSetContext


def get_loadout_file(runtime_dir: str | Path, character_id: str) -> Path:
    p = Path(runtime_dir).resolve() / "loadouts" / f"{character_id}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_loadout(runtime_dir: str | Path, character_id: str) -> EquippedLoadout:
    target = get_loadout_file(runtime_dir, character_id)
    if target.exists():
        try:
            return EquippedLoadout.model_validate_json(target.read_text(encoding="utf-8"))
        except Exception:
            pass
    return EquippedLoadout.create_draft(character_id=character_id)


def save_loadout(runtime_dir: str | Path, loadout: EquippedLoadout) -> Path:
    target = get_loadout_file(runtime_dir, loadout.character_id)
    raw_bytes = (loadout.model_dump_json(indent=2) + "\n").encode("utf-8")
    atomic_write_file(target, raw_bytes)
    return target


def run_loadout_set_item(
    runtime_dir: str | Path,
    character_id: str,
    slot_name: str,
    item_text: str,
    weapon_set_name: str | None = None,
    source: BaselineSource = BaselineSource.CLIPBOARD_ITEM_TEXT,
) -> EquippedLoadout:
    loadout = load_loadout(runtime_dir, character_id)
    slot = SlotType.from_str(slot_name)
    wset = WeaponSetContext.from_val(weapon_set_name) if weapon_set_name else None

    item = parse_item_text(item_text, target_slot=slot, target_weapon_set=wset)
    loadout.set_slot(slot=slot, item=item, source=source, weapon_set=wset)
    save_loadout(runtime_dir, loadout)
    return loadout


def run_loadout_finalize(
    runtime_dir: str | Path,
    character_id: str,
    loadout_id: str | None = None,
) -> EquippedLoadout:
    loadout = load_loadout(runtime_dir, character_id)
    loadout.finalize(loadout_id=loadout_id)
    save_loadout(runtime_dir, loadout)
    return loadout


def run_loadout_clear(
    runtime_dir: str | Path,
    character_id: str,
    slot_name: str,
    weapon_set_name: str | None = None,
) -> EquippedLoadout:
    loadout = load_loadout(runtime_dir, character_id)
    slot = SlotType.from_str(slot_name)
    wset = WeaponSetContext.from_val(weapon_set_name) if weapon_set_name else None
    loadout.clear_slot(slot=slot, weapon_set=wset)
    save_loadout(runtime_dir, loadout)
    return loadout


def run_loadout_show(
    runtime_dir: str | Path,
    character_id: str,
) -> str:
    loadout = load_loadout(runtime_dir, character_id)
    lines: list[str] = [
        f"=== Equipped Loadout: {loadout.loadout_id} ===",
        f"Character ID: {loadout.character_id}",
        f"Revision: {loadout.revision} (Finalized: {loadout.is_finalized})",
        f"Updated At: {loadout.updated_at}",
        "--- Shared Slots ---",
    ]

    for slot in ALL_SHARED_SLOTS:
        entry = loadout.shared_slots.get(slot.value)
        if entry and entry.item:
            lines.append(f"  {slot.value.upper()}: {entry.item.name} ({entry.item.base_type}) [{entry.verification.value}]")
        else:
            lines.append(f"  {slot.value.upper()}: <EMPTY/UNKNOWN>")

    lines.append("--- Weapon Set 1 ---")
    for slot in ALL_WEAPON_SLOTS:
        entry = loadout.weapon_set_1.get(slot.value)
        if entry and entry.item:
            lines.append(f"  {slot.value.upper()}: {entry.item.name} ({entry.item.base_type}) [{entry.verification.value}]")
        else:
            lines.append(f"  {slot.value.upper()}: <EMPTY/UNKNOWN>")

    lines.append("--- Weapon Set 2 ---")
    for slot in ALL_WEAPON_SLOTS:
        entry = loadout.weapon_set_2.get(slot.value)
        if entry and entry.item:
            lines.append(f"  {slot.value.upper()}: {entry.item.name} ({entry.item.base_type}) [{entry.verification.value}]")
        else:
            lines.append(f"  {slot.value.upper()}: <EMPTY/UNKNOWN>")

    return "\n".join(lines)
