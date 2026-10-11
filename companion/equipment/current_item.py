"""Read the currently equipped item (PoB2 session first, then the saved loadout)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_current_raw(
    runtime_dir: Path,
    char_id: str,
    slot_name: str,
    pob_session: Any | None = None,
) -> str:
    """Retrieve raw text of equipped item for given slot, from PoB session or local loadout."""
    if pob_session is not None:
        pob_slot_candidates = [slot_name]
        try:
            from companion.equipment.schema import SlotType
            st = SlotType.from_str(slot_name)
            pob_mapping = {
                SlotType.HELMET: "Helmet",
                SlotType.BODY_ARMOUR: "Body Armour",
                SlotType.GLOVES: "Gloves",
                SlotType.BOOTS: "Boots",
                SlotType.AMULET: "Amulet",
                SlotType.RING_1: "Ring 1",
                SlotType.RING_2: "Ring 2",
                SlotType.BELT: "Belt",
                SlotType.MAIN_HAND: "Weapon 1",
                SlotType.OFF_HAND: "Weapon 2",
            }
            if st in pob_mapping and pob_mapping[st] not in pob_slot_candidates:
                pob_slot_candidates.insert(0, pob_mapping[st])
        except Exception:
            logger.debug("Slot name %r not mapped to a PoB slot", slot_name, exc_info=True)

        for p_slot in pob_slot_candidates:
            try:
                eq = pob_session.get_equipped_item(p_slot)
                if isinstance(eq, dict) and eq.get("raw"):
                    from companion.equipment.pob_item_text import pob_item_to_clipboard
                    return pob_item_to_clipboard(eq["raw"])
            except Exception:  # includes PobItemTextError: fall back to the loadout text
                logger.debug("PoB equipped item unreadable for %s", p_slot, exc_info=True)

    try:
        from companion.equipment.loadout_cli import load_loadout
        from companion.equipment.schema import SlotType, WeaponSetContext
        lo = load_loadout(runtime_dir, char_id)
        if lo:
            w_ctx = None
            norm = slot_name.lower().strip()
            if "set2" in norm or "swap" in norm:
                w_ctx = WeaponSetContext.WEAPON_SET_2
            elif "set1" in norm:
                w_ctx = WeaponSetContext.WEAPON_SET_1

            try:
                st, w_ctx = _swap_slot(slot_name, w_ctx)
                entry = lo.get_slot(st, weapon_set=w_ctx)
                if entry and entry.item and entry.item.raw_text:
                    return entry.item.raw_text
            except Exception:
                logger.debug("Loadout lookup failed for %s", slot_name, exc_info=True)

            direct_keys = [
                slot_name.lower().replace(" ", "_"),
                slot_name.lower().replace(" ", "").replace("_", ""),
            ]
            for dk in direct_keys:
                entry = lo.shared_slots.get(dk)
                if entry and entry.item and entry.item.raw_text:
                    return entry.item.raw_text
    except Exception:
        logger.warning("Loadout read failed for %s", char_id, exc_info=True)
    return ""


_SWAP_SLOTS = {"weapon 1 swap": "MAIN_HAND", "weapon 2 swap": "OFF_HAND"}


def _swap_slot(slot_name: str, w_ctx: Any) -> tuple[Any, Any]:
    """Resolve a slot name to (SlotType, weapon set); canonical swap names mean Weapon Set 2."""
    from companion.equipment.schema import SlotType, WeaponSetContext
    swap = _SWAP_SLOTS.get(slot_name.lower().strip())
    if swap:
        return SlotType[swap], WeaponSetContext.WEAPON_SET_2
    return SlotType.from_str(slot_name), w_ctx


def get_current_item_info(
    runtime_dir: Path,
    char_id: str,
    slot_name: str,
    pob_session: Any | None = None,
) -> tuple[str, str]:
    """Retrieve (item_name, base_type) of equipped item for given slot."""
    # 1. PoB session if available
    if pob_session is not None:
        try:
            p_name = pob_session.get_current_item_name(slot_name)
            if p_name and p_name != "Unobserved":
                return str(p_name), ""
        except Exception:
            logger.debug("PoB current item name unavailable for %s", slot_name, exc_info=True)

    # 2. Local loadout
    try:
        from companion.equipment.loadout_cli import load_loadout
        from companion.equipment.schema import SlotType, WeaponSetContext
        lo = load_loadout(runtime_dir, char_id)
        if lo:
            w_ctx = None
            norm = slot_name.lower().strip()
            if "set2" in norm or "swap" in norm:
                w_ctx = WeaponSetContext.WEAPON_SET_2
            elif "set1" in norm:
                w_ctx = WeaponSetContext.WEAPON_SET_1

            try:
                st, w_ctx = _swap_slot(slot_name, w_ctx)
                entry = lo.get_slot(st, weapon_set=w_ctx)
                if entry and entry.item and (entry.item.name or entry.item.base_type):
                    return entry.item.name or entry.item.base_type, entry.item.base_type or ""
            except Exception:
                logger.debug("Loadout lookup failed for %s", slot_name, exc_info=True)

            direct_keys = [
                slot_name.lower().replace(" ", "_"),
                slot_name.lower().replace(" ", "").replace("_", ""),
            ]
            for dk in direct_keys:
                entry = lo.shared_slots.get(dk)
                if entry and entry.item and (entry.item.name or entry.item.base_type):
                    return entry.item.name or entry.item.base_type, entry.item.base_type or ""
    except Exception:
        logger.warning("Loadout read failed for %s", char_id, exc_info=True)

    # 3. Parse current raw item text
    try:
        raw = get_current_raw(runtime_dir, char_id, slot_name, pob_session)
        if raw:
            from companion.equipment.parser import parse_item_text
            parsed = parse_item_text(raw)
            if parsed.name or parsed.base_type:
                return parsed.name or parsed.base_type, parsed.base_type or ""
    except Exception:
        logger.debug("Current item parse failed for %s", slot_name, exc_info=True)

    return "Slot Kosong", ""


def character_level_and_zone(char_data: dict[str, Any]) -> tuple[int | None, str | None]:
    """Read level and current_zone from character JSON (each either {"value": x} or plain)."""
    def plain(v: Any) -> Any:
        return v.get("value") if isinstance(v, dict) else v

    lvl, zone = plain(char_data.get("level")), plain(char_data.get("current_zone"))
    return (lvl if isinstance(lvl, int) else None), (zone if isinstance(zone, str) else None)
