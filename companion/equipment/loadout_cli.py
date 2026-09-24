"""CLI handlers and storage operations for EquippedLoadout."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable
from pydantic import BaseModel, ConfigDict, Field

from companion.state.store import atomic_write_file
from companion.equipment.baseline import BaselineSource, CharacterStatBaseline
from companion.equipment.parser import parse_item_text
from companion.equipment.loadout import (
    ALL_SHARED_SLOTS,
    ALL_WEAPON_SLOTS,
    EquippedLoadout,
    is_item_decision_equal,
)
from companion.equipment.loadout_promotion import promote_candidate_to_loadout
from companion.equipment.schema import ItemCandidate, SlotOccupancy, SlotType, WeaponSetContext


def get_loadout_file(runtime_dir: str | Path, character_id: str) -> Path:
    p = Path(runtime_dir).resolve() / "loadouts" / f"{character_id}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_loadout_history_dir(runtime_dir: str | Path, character_id: str) -> Path:
    p = Path(runtime_dir).resolve() / "loadout_history" / character_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_loadout_history_file(runtime_dir: str | Path, character_id: str, revision: int) -> Path:
    return get_loadout_history_dir(runtime_dir, character_id) / f"rev_{revision:06d}.json"


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


def load_loadout_history(runtime_dir: str | Path, character_id: str, revision: int) -> EquippedLoadout | None:
    """Load a prior revision snapshot from loadout history."""
    target = get_loadout_history_file(runtime_dir, character_id, revision)
    if target.exists():
        try:
            return EquippedLoadout.model_validate_json(target.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_loadout_history_snapshot(runtime_dir: str | Path, loadout: EquippedLoadout) -> Path:
    """Save an immutable snapshot of a finalized loadout revision."""
    target = get_loadout_history_file(runtime_dir, loadout.character_id, loadout.revision)
    raw_bytes = (loadout.model_dump_json(indent=2) + "\n").encode("utf-8")
    atomic_write_file(target, raw_bytes)
    return target


class LoadoutTransitionResult(BaseModel):
    """Metadata describing the outcome of an authoritative loadout transition."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    loadout: EquippedLoadout
    previous_revision: int
    new_revision: int
    is_changed: bool
    is_finalized: bool
    history_snapshot_path: Path | None = None


def execute_loadout_transition(
    runtime_dir: str | Path,
    character_id: str,
    mutation_fn: Callable[[EquippedLoadout], bool],
) -> LoadoutTransitionResult:
    """Authoritative, centralized post-finalization mutation transition path.

    Steps:
    1. Load current loadout state.
    2. Determine whether decision-relevant content actually changes.
    3. If unchanged:
       - No revision increment, no history write.
    4. If changed and draft:
       - Mutate draft normally without revision increment.
    5. If changed and finalized:
       - Preserve prior revision snapshot in loadout_history.
       - Increment revision exactly once.
       - Persist new revision atomically.
       - Keep is_finalized = True, update updated_at.
    """
    loadout = load_loadout(runtime_dir, character_id)
    prior_copy = loadout.model_copy(deep=True)
    prev_rev = prior_copy.revision
    prev_finalized = prior_copy.is_finalized

    is_changed = mutation_fn(loadout)

    if not is_changed:
        res = LoadoutTransitionResult(
            loadout=loadout,
            previous_revision=prev_rev,
            new_revision=prev_rev,
            is_changed=False,
            is_finalized=prev_finalized,
            history_snapshot_path=None,
        )
        setattr(loadout, "last_transition", res)
        return res

    if not prev_finalized:
        loadout.updated_at = datetime.now(timezone.utc).isoformat()
        save_loadout(runtime_dir, loadout)
        res = LoadoutTransitionResult(
            loadout=loadout,
            previous_revision=prev_rev,
            new_revision=loadout.revision,
            is_changed=True,
            is_finalized=False,
            history_snapshot_path=None,
        )
        setattr(loadout, "last_transition", res)
        return res

    # Finalized and changed:
    # 1. Snapshot prior revision
    snap_path = save_loadout_history_snapshot(runtime_dir, prior_copy)

    # 2. Advance revision exactly once
    loadout.revision = prev_rev + 1
    loadout.is_finalized = True
    loadout.updated_at = datetime.now(timezone.utc).isoformat()

    # 3. Atomically persist
    save_loadout(runtime_dir, loadout)

    res = LoadoutTransitionResult(
        loadout=loadout,
        previous_revision=prev_rev,
        new_revision=loadout.revision,
        is_changed=True,
        is_finalized=True,
        history_snapshot_path=snap_path,
    )
    setattr(loadout, "last_transition", res)
    return res


def run_loadout_set_item(
    runtime_dir: str | Path,
    character_id: str,
    slot_name: str,
    item_text: str,
    weapon_set_name: str | None = None,
    source: BaselineSource = BaselineSource.CLIPBOARD_ITEM_TEXT,
) -> EquippedLoadout:
    """Set an item in an equipped loadout slot via centralized transition path."""
    slot = SlotType.from_str(slot_name)
    wset = WeaponSetContext.from_val(weapon_set_name) if weapon_set_name else None
    item = parse_item_text(item_text, target_slot=slot, target_weapon_set=wset)

    def mutate(l: EquippedLoadout) -> bool:
        existing = l.get_slot(slot, weapon_set=wset)
        current_item = existing.item if existing else None
        if is_item_decision_equal(current_item, item):
            return False
        l._raw_set_slot(slot=slot, item=item, source=source, weapon_set=wset)
        return True

    trans_result = execute_loadout_transition(runtime_dir, character_id, mutate)
    return trans_result.loadout


def run_loadout_clear(
    runtime_dir: str | Path,
    character_id: str,
    slot_name: str,
    weapon_set_name: str | None = None,
) -> EquippedLoadout:
    """Clear an equipped loadout slot via centralized transition path."""
    slot = SlotType.from_str(slot_name)
    wset = WeaponSetContext.from_val(weapon_set_name) if weapon_set_name else None

    def mutate(l: EquippedLoadout) -> bool:
        existing = l.get_slot(slot, weapon_set=wset)
        if existing is None or existing.item is None:
            return False
        l._raw_clear_slot(slot=slot, weapon_set=wset)
        return True

    trans_result = execute_loadout_transition(runtime_dir, character_id, mutate)
    return trans_result.loadout


def run_loadout_promote_candidate(
    runtime_dir: str | Path,
    character_id: str,
    slot_name: str,
    candidate_text: str,
    weapon_set_name: str | None = None,
) -> tuple[EquippedLoadout, CharacterStatBaseline | None]:
    """Promote candidate into loadout via authoritative mutation transition path.

    - Increments revision exactly once if changed and finalized.
    - Preserves prior revision snapshot in history.
    - Reconciles baseline if baseline exists on disk, anchoring new revision and fingerprint.
    """
    from companion.equipment.baseline_cli import get_baseline_file, load_baseline, save_baseline

    slot = SlotType.from_str(slot_name)
    wset = WeaponSetContext.from_val(weapon_set_name) if weapon_set_name else None
    candidate = parse_item_text(candidate_text, target_slot=slot, target_weapon_set=wset)

    loadout = load_loadout(runtime_dir, character_id)
    baseline = load_baseline(runtime_dir, character_id)
    prior_copy = loadout.model_copy(deep=True)

    # Determine whether content actually changes
    current_entry = prior_copy.get_slot(slot, weapon_set=wset)
    current_item = current_entry.item if current_entry else None

    conflicting_entries: list[tuple[SlotType, ItemCandidate]] = []
    if candidate.slot_occupancy == SlotOccupancy.TWO_HAND and wset in (WeaponSetContext.WEAPON_SET_1, WeaponSetContext.WEAPON_SET_2):
        for conflict_slot in candidate.slot_conflict_topology.conflicting_slots:
            if conflict_slot != slot:
                conflict_entry = prior_copy.get_slot(conflict_slot, weapon_set=wset)
                if conflict_entry and conflict_entry.item:
                    conflicting_entries.append((conflict_slot, conflict_entry.item))

    is_changed = not (is_item_decision_equal(current_item, candidate) and len(conflicting_entries) == 0)

    # Snapshot rev N before advancing to rev N+1
    snap_path: Path | None = None
    if is_changed and prior_copy.is_finalized:
        snap_path = save_loadout_history_snapshot(runtime_dir, prior_copy)

    # Use promote_candidate_to_loadout to determine change and perform promotion
    new_loadout, new_baseline = promote_candidate_to_loadout(
        loadout=loadout,
        candidate=candidate,
        slot=slot,
        baseline=baseline,
        weapon_set=wset,
    )

    if is_changed:
        new_loadout.updated_at = datetime.now(timezone.utc).isoformat()

    trans_result = LoadoutTransitionResult(
        loadout=new_loadout,
        previous_revision=prior_copy.revision,
        new_revision=new_loadout.revision,
        is_changed=is_changed,
        is_finalized=prior_copy.is_finalized,
        history_snapshot_path=snap_path,
    )
    setattr(new_loadout, "last_transition", trans_result)

    save_loadout(runtime_dir, new_loadout)
    if new_baseline:
        save_baseline(runtime_dir, new_baseline)

    return new_loadout, new_baseline


def run_loadout_finalize(
    runtime_dir: str | Path,
    character_id: str,
    loadout_id: str | None = None,
) -> EquippedLoadout:
    loadout = load_loadout(runtime_dir, character_id)
    loadout.finalize(loadout_id=loadout_id)
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
        f"Fingerprint: {loadout.compute_fingerprint()[:16]}...",
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
