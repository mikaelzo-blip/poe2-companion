"""Server-side slot resolution: which canonical slots an item should be tried in."""

from __future__ import annotations

import re

from pydantic import BaseModel

from companion.builds.guide import GuideStage, singular_item_class
from companion.equipment.pob2_equipment_advisor import normalize_and_validate_pob_slot
from companion.equipment.schema import ItemCandidate, SlotOccupancy, SlotType, WeaponSetContext
from companion.equipment.weapon_topology import WeaponTopologyResolver

UI_SLOT_KEYS: dict[str, str] = {
    "Weapon 1": "main_hand",
    "Weapon 2": "off_hand",
    "Weapon 1 Swap": "set2_main_hand",
    "Weapon 2 Swap": "set2_off_hand",
    "Ring 1": "ring1",
    "Ring 2": "ring2",
    "Body Armour": "body_armour",
    "Helmet": "helmet",
    "Gloves": "gloves",
    "Boots": "boots",
    "Amulet": "amulet",
    "Belt": "belt",
}
_FROM_UI = {v: k for k, v in UI_SLOT_KEYS.items()}
_EXTRA_ALIASES = {"swap_main_hand": "Weapon 1 Swap", "swap_off_hand": "Weapon 2 Swap"}
_NON_EQUIPPABLE = ("Jewel", "Flask", "Charm", "Waystone")
_ITEM_CLASS_RE = re.compile(r"^Item Class:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_SET_CONTEXT = {1: WeaponSetContext.WEAPON_SET_1, 2: WeaponSetContext.WEAPON_SET_2}


class SlotPlan(BaseModel):
    slot: str
    clear_slots: tuple[str, ...] = ()


def canonical_slot(name: str) -> str:
    key = (name or "").strip().lower().replace(" ", "_")
    if key in _FROM_UI:
        return _FROM_UI[key]
    if key in _EXTRA_ALIASES:
        return _EXTRA_ALIASES[key]
    try:
        return normalize_and_validate_pob_slot(name)
    except ValueError:
        raise ValueError(f"Slot tidak dikenal: {name}") from None


def item_class_of(raw_text: str) -> str:
    m = _ITEM_CLASS_RE.search(raw_text or "")
    return singular_item_class(m.group(1)) if m else ""


def _weapon_sets(item_class: str, stage: GuideStage) -> list[int]:
    matching = [n for n in (1, 2) if item_class in stage.weapon_classes.get(n, [])]
    return matching if len(matching) == 1 else [1, 2]


def _candidate_plans(candidate: ItemCandidate, item_class: str, stage: GuideStage) -> tuple[list[SlotPlan], str]:
    slot = candidate.slot
    if slot in (SlotType.MAIN_HAND, SlotType.OFF_HAND):
        sets = _weapon_sets(item_class, stage)
        topo = WeaponTopologyResolver()
        plans: list[SlotPlan] = []
        for n in sets:
            main, off = topo.get_set_slots(_SET_CONTEXT[n])
            if candidate.slot_occupancy == SlotOccupancy.TWO_HAND:
                plans.append(SlotPlan(slot=main, clear_slots=topo.resolve_topology(candidate, _SET_CONTEXT[n]).clear_slots))
            elif slot == SlotType.OFF_HAND:
                plans.append(SlotPlan(slot=off))
            else:
                plans += [SlotPlan(slot=main), SlotPlan(slot=off)]
        if len(sets) == 1:
            return plans, f"{item_class} dipakai guide di Weapon Set {sets[0]}"
        return plans, f"{item_class}: dicoba di Weapon Set 1 dan 2"
    if slot in (SlotType.RING_1, SlotType.RING_2):
        return [SlotPlan(slot="Ring 1"), SlotPlan(slot="Ring 2")], "Cincin: dicoba di Ring 1 dan Ring 2"
    canon = normalize_and_validate_pob_slot(slot)
    return [SlotPlan(slot=canon)], f"Slot: {canon}"


def resolve_slots(
    candidate: ItemCandidate, item_class: str, stage: GuideStage, locked_slot: str | None = None
) -> tuple[list[SlotPlan], str]:
    if candidate.slot is None or any(item_class.endswith(c) for c in _NON_EQUIPPABLE):
        raise ValueError("Item ini tidak bisa dipasang di slot equipment")
    plans, reason = _candidate_plans(candidate, item_class, stage)
    if locked_slot:
        locked = canonical_slot(locked_slot)
        plans = [p for p in plans if p.slot == locked]
        if not plans:
            raise ValueError("Slot terkunci tidak cocok dengan item")
        reason = f"Slot dikunci: {locked}"
    return plans, reason
