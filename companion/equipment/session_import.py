"""Persist a synced PoB2 session's item text and computed stats into the runtime."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from companion.equipment.baseline import BaselineSource, CharacterFact, CharacterStatBaseline
from companion.equipment.baseline_cli import load_baseline, save_baseline
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.loadout_cli import (
    character_runtime_lock, execute_loadout_transition, load_loadout, save_loadout,
)
from companion.equipment.parser import parse_item_text
from companion.equipment.pob2_equipment_advisor import POB2_PRODUCTION_SLOTS
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.state.provenance import VerificationState

logger = logging.getLogger(__name__)

_SET1, _SET2 = WeaponSetContext.WEAPON_SET_1, WeaponSetContext.WEAPON_SET_2
_SLOT_MAP: dict[str, tuple[SlotType, WeaponSetContext | None]] = {
    "Helmet": (SlotType.HELMET, None),
    "Body Armour": (SlotType.BODY_ARMOUR, None),
    "Gloves": (SlotType.GLOVES, None),
    "Boots": (SlotType.BOOTS, None),
    "Amulet": (SlotType.AMULET, None),
    "Ring 1": (SlotType.RING_1, None),
    "Ring 2": (SlotType.RING_2, None),
    "Belt": (SlotType.BELT, None),
    "Weapon 1": (SlotType.MAIN_HAND, _SET1),
    "Weapon 2": (SlotType.OFF_HAND, _SET1),
    "Weapon 1 Swap": (SlotType.MAIN_HAND, _SET2),
    "Weapon 2 Swap": (SlotType.OFF_HAND, _SET2),
}
_DEFENSE_FIELDS = {
    "life": "Life", "armour": "Armour", "evasion": "Evasion",
    "energy_shield": "EnergyShield", "mana": "Mana",
}


def _parse_items(equipped: dict[str, Any], warnings: list[str]) -> list[tuple[SlotType, WeaponSetContext | None, Any]]:
    parsed = []
    for pob_slot in sorted(POB2_PRODUCTION_SLOTS):
        mapped = _SLOT_MAP.get(pob_slot)
        eq = equipped.get(pob_slot)
        if mapped is None or not eq or not eq.get("equipped") or not eq.get("raw"):
            continue
        slot, wset = mapped
        try:
            parsed.append((slot, wset, parse_item_text(eq["raw"], target_slot=slot, target_weapon_set=wset)))
        except Exception as exc:
            logger.warning("PoB2 item import failed for %s", pob_slot, exc_info=True)
            warnings.append(f"{pob_slot}: could not import item ({exc})")
    return parsed


def _apply_items(loadout: EquippedLoadout, parsed: list) -> bool:
    """Mutate loadout in place; True if a decision-relevant change occurred."""
    changed = False
    for slot, wset, item in parsed:
        if loadout.transition_slot(
            slot, item, source=BaselineSource.GGG_OFFICIAL_API, weapon_set=wset,
            verification=VerificationState.VERIFIED,
        ):
            changed = True
        else:
            loadout.refresh_slot_text(slot, item.raw_text, weapon_set=wset)
    return changed


def _set_fact(baseline: CharacterStatBaseline, attr: str, value: Any) -> None:
    old = getattr(baseline, attr)
    if old.source == BaselineSource.MANUAL_USER_INPUT and old.value is not None:
        return
    setattr(baseline, attr, CharacterFact[int].create(
        int(value), source=BaselineSource.DERIVED_CALCULATION, evidence_ref="pob2",
        verification=VerificationState.VERIFIED,
    ))


def _apply_baseline(baseline: CharacterStatBaseline, defenses: dict, stats: dict) -> None:
    for attr, key in _DEFENSE_FIELDS.items():
        if defenses.get(key) is not None:
            _set_fact(baseline, attr, defenses[key])
    stats = stats.get("defense") or {}
    for el in ("fire", "cold", "lightning", "chaos"):
        raw = stats.get(f"{el.capitalize()}Resist")
        if raw is None:
            continue
        cap = getattr(baseline, f"max_{el}_res").value or 75
        _set_fact(baseline, f"raw_{el}_res", raw)
        _set_fact(baseline, f"effective_{el}_res", min(int(raw), cap))


def _snapshot(session: Any) -> tuple[dict, dict, dict]:
    """Copy cached session data while no sync is mutating it (never calls engine methods)."""
    with session._engine_lock:
        return (
            dict(session.equipped_items or {}),
            dict(session.defenses_before or {}),
            dict(session.stats_before or {}),
        )


def apply_session_to_runtime(runtime_dir: Path, character_id: str, session: Any) -> list[str]:
    """Write the session's equipped item text and computed baseline; returns warnings, never raises."""
    warnings: list[str] = []
    try:
        equipped, defenses, stats = _snapshot(session)
        parsed = _parse_items(equipped, warnings)
        with character_runtime_lock(character_id):
            loadout = load_loadout(runtime_dir, character_id)
            if loadout.is_finalized:
                res = execute_loadout_transition(
                    runtime_dir, character_id, lambda lo: _apply_items(lo, parsed)
                )
                loadout = res.loadout
                if not res.is_changed:
                    save_loadout(runtime_dir, loadout)  # raw_text refreshes carry no revision bump
            else:
                _apply_items(loadout, parsed)
                loadout.finalize(loadout_id=f"pob2_{character_id}")
                save_loadout(runtime_dir, loadout)

            baseline = load_baseline(runtime_dir, character_id) or CharacterStatBaseline(
                baseline_id=f"pob2_{character_id}", character_id=character_id,
                anchored_loadout_revision=loadout.revision,
            )
            baseline.anchored_loadout_revision = loadout.revision
            baseline.anchored_loadout_fingerprint = loadout.compute_fingerprint()
            _apply_baseline(baseline, defenses, stats)
            save_baseline(runtime_dir, baseline)
    except Exception as exc:
        logger.warning("apply_session_to_runtime failed for %s", character_id, exc_info=True)
        warnings.append(f"runtime update failed: {exc}")
    return warnings
