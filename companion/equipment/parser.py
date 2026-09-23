"""PoE2 item text parser for manual clipboard ingestion and candidate evaluation."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from companion.equipment.normalizer import normalize_modifier
from companion.equipment.schema import (
    ItemCandidate,
    NormalizedModifier,
    SlotConflictTopology,
    SlotOccupancy,
    SlotType,
    WeaponSetContext,
)

RE_ITEM_CLASS = re.compile(r"^Item Class:\s*(.+)$", re.IGNORECASE)
RE_RARITY = re.compile(r"^Rarity:\s*(.+)$", re.IGNORECASE)
RE_ARMOUR = re.compile(r"^Armour:\s*(\d+)", re.IGNORECASE)
RE_EVASION = re.compile(r"^Evasion(?:\s+Rating)?:\s*(\d+)", re.IGNORECASE)
RE_ENERGY_SHIELD = re.compile(r"^Energy\s+Shield:\s*(\d+)", re.IGNORECASE)
RE_ITEM_LEVEL = re.compile(r"^Item\s+Level:\s*(\d+)", re.IGNORECASE)

RE_REQ_LEVEL = re.compile(r"^\s*Level:\s*(\d+)", re.IGNORECASE)
RE_REQ_STR = re.compile(r"^\s*Str(?:ength)?:\s*(\d+)", re.IGNORECASE)
RE_REQ_DEX = re.compile(r"^\s*Dex(?:terity)?:\s*(\d+)", re.IGNORECASE)
RE_REQ_INT = re.compile(r"^\s*Int(?:elligence)?:\s*(\d+)", re.IGNORECASE)


def parse_slot_topology_for_base(
    item_class: str,
    base_type: str,
    target_slot: SlotType | None = None,
    target_weapon_set: WeaponSetContext | None = None,
) -> tuple[SlotType, SlotOccupancy, SlotConflictTopology]:
    """Derive SlotType, SlotOccupancy, and SlotConflictTopology from item class and base."""
    cls_lower = item_class.lower().strip()
    base_lower = base_type.lower().strip()

    # Shared equipment
    if "boot" in cls_lower or "boots" in base_lower:
        slot = SlotType.BOOTS
        return slot, SlotOccupancy.SINGLE_SLOT, SlotConflictTopology(
            occupied_slots=[slot],
            conflicting_slots=[slot],
            is_known=True,
        )
    if "glove" in cls_lower or "gloves" in base_lower or "gauntlet" in base_lower:
        slot = SlotType.GLOVES
        return slot, SlotOccupancy.SINGLE_SLOT, SlotConflictTopology(
            occupied_slots=[slot],
            conflicting_slots=[slot],
            is_known=True,
        )
    if "helmet" in cls_lower or "helm" in cls_lower or "helmet" in base_lower or "circlet" in base_lower:
        slot = SlotType.HELMET
        return slot, SlotOccupancy.SINGLE_SLOT, SlotConflictTopology(
            occupied_slots=[slot],
            conflicting_slots=[slot],
            is_known=True,
        )
    if "body armour" in cls_lower or "chest" in cls_lower or "armour" in cls_lower or "vest" in base_lower or "robe" in base_lower or "mail" in base_lower or "cuirass" in base_lower:
        slot = SlotType.BODY_ARMOUR
        return slot, SlotOccupancy.SINGLE_SLOT, SlotConflictTopology(
            occupied_slots=[slot],
            conflicting_slots=[slot],
            is_known=True,
        )
    if "amulet" in cls_lower or "amulet" in base_lower:
        slot = SlotType.AMULET
        return slot, SlotOccupancy.SINGLE_SLOT, SlotConflictTopology(
            occupied_slots=[slot],
            conflicting_slots=[slot],
            is_known=True,
        )
    if "ring" in cls_lower or "ring" in base_lower:
        slot = target_slot if target_slot in (SlotType.RING_1, SlotType.RING_2) else SlotType.RING_1
        return slot, SlotOccupancy.SINGLE_SLOT, SlotConflictTopology(
            occupied_slots=[slot],
            conflicting_slots=[slot],
            is_known=True,
        )
    if "belt" in cls_lower or "belt" in base_lower or "sash" in base_lower:
        slot = SlotType.BELT
        return slot, SlotOccupancy.SINGLE_SLOT, SlotConflictTopology(
            occupied_slots=[slot],
            conflicting_slots=[slot],
            is_known=True,
        )

    # Two Hand Staves (Fubgun Set 1)
    if "staff" in cls_lower or "staves" in cls_lower or "staff" in base_lower:
        slot = SlotType.MAIN_HAND
        return slot, SlotOccupancy.TWO_HAND, SlotConflictTopology(
            occupied_slots=[SlotType.MAIN_HAND, SlotType.OFF_HAND],
            conflicting_slots=[SlotType.MAIN_HAND, SlotType.OFF_HAND],
            allowed_companion_slots=[],
            is_known=True,
        )

    # Crossbows (Fubgun Set 2: NO quiver, occupies both slots)
    if "crossbow" in cls_lower or "crossbow" in base_lower:
        slot = SlotType.MAIN_HAND
        return slot, SlotOccupancy.TWO_HAND, SlotConflictTopology(
            occupied_slots=[SlotType.MAIN_HAND, SlotType.OFF_HAND],
            conflicting_slots=[SlotType.MAIN_HAND, SlotType.OFF_HAND],
            allowed_companion_slots=[],  # Quiver forbidden
            is_known=True,
        )

    # Bows (Allows Quiver)
    if "bow" in cls_lower or "bow" in base_lower:
        slot = SlotType.MAIN_HAND
        return slot, SlotOccupancy.TWO_HAND, SlotConflictTopology(
            occupied_slots=[SlotType.MAIN_HAND, SlotType.OFF_HAND],
            conflicting_slots=[SlotType.MAIN_HAND, SlotType.OFF_HAND],
            allowed_companion_slots=[SlotType.OFF_HAND],
            is_known=True,
        )

    # Quivers (Off Hand, requires Bow)
    if "quiver" in cls_lower or "quiver" in base_lower:
        slot = SlotType.OFF_HAND
        return slot, SlotOccupancy.OFF_HAND, SlotConflictTopology(
            occupied_slots=[SlotType.OFF_HAND],
            conflicting_slots=[SlotType.OFF_HAND],
            allowed_companion_slots=[],
            is_known=True,
        )

    # Shields (Off Hand)
    if "shield" in cls_lower or "shield" in base_lower or "buckler" in base_lower:
        slot = SlotType.OFF_HAND
        return slot, SlotOccupancy.OFF_HAND, SlotConflictTopology(
            occupied_slots=[SlotType.OFF_HAND],
            conflicting_slots=[SlotType.OFF_HAND],
            allowed_companion_slots=[],
            is_known=True,
        )

    # One Hand Weapons (Wands, Sceptres, Daggers, Swords, Maces, Flails)
    if any(k in cls_lower or k in base_lower for k in ("wand", "sceptre", "dagger", "sword", "mace", "flail")):
        slot = target_slot if target_slot in (SlotType.MAIN_HAND, SlotType.OFF_HAND) else SlotType.MAIN_HAND
        return slot, SlotOccupancy.MAIN_HAND, SlotConflictTopology(
            occupied_slots=[slot],
            conflicting_slots=[slot],
            allowed_companion_slots=[SlotType.OFF_HAND],
            is_known=True,
        )

    # Fallback: Unknown
    fallback_slot = target_slot or SlotType.HELMET
    return fallback_slot, SlotOccupancy.UNKNOWN_OCCUPANCY, SlotConflictTopology(
        occupied_slots=[],
        conflicting_slots=[],
        allowed_companion_slots=[],
        is_known=False,
    )


def parse_item_text(
    raw_text: str,
    target_slot: SlotType | None = None,
    target_weapon_set: WeaponSetContext | None = None,
) -> ItemCandidate:
    """Parse standard PoE2 item clipboard text into ItemCandidate."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Cannot parse empty item text")

    # Group sections delimited by dashed lines
    sections: list[list[str]] = []
    current_section: list[str] = []
    for line in lines:
        if line.startswith("---") or line.startswith("==="):
            if current_section:
                sections.append(current_section)
                current_section = []
        else:
            current_section.append(line)
    if current_section:
        sections.append(current_section)

    item_class = ""
    rarity = "normal"
    name = ""
    base_type = ""
    local_armour = 0
    local_evasion = 0
    local_energy_shield = 0
    item_level: int | None = None
    req_level = 1
    req_str = 0
    req_dex = 0
    req_int = 0

    header_lines = sections[0] if sections else []
    rem_header: list[str] = []

    for line in header_lines:
        m_cls = RE_ITEM_CLASS.match(line)
        if m_cls:
            item_class = m_cls.group(1).strip()
            continue
        m_rar = RE_RARITY.match(line)
        if m_rar:
            rarity = m_rar.group(1).strip().lower()
            continue
        rem_header.append(line)

    if len(rem_header) >= 2:
        name = rem_header[0]
        base_type = rem_header[1]
    elif len(rem_header) == 1:
        name = rem_header[0]
        base_type = rem_header[0]
    else:
        name = "Unknown Item"
        base_type = "Unknown Base"

    # Process remaining sections
    modifier_lines: list[tuple[str, bool]] = []
    in_requirements = False

    for section in sections[1:]:
        first_line = section[0]
        if first_line.lower().startswith("requirements:"):
            for rline in section[1:]:
                m = RE_REQ_LEVEL.search(rline)
                if m:
                    req_level = int(m.group(1))
                m = RE_REQ_STR.search(rline)
                if m:
                    req_str = int(m.group(1))
                m = RE_REQ_DEX.search(rline)
                if m:
                    req_dex = int(m.group(1))
                m = RE_REQ_INT.search(rline)
                if m:
                    req_int = int(m.group(1))
            continue

        if any(RE_ITEM_LEVEL.match(l) for l in section):
            for l in section:
                m = RE_ITEM_LEVEL.match(l)
                if m:
                    item_level = int(m.group(1))
            continue

        # Check for local property block (Armour, Evasion, etc.)
        is_prop_section = False
        for l in section:
            m = RE_ARMOUR.match(l)
            if m:
                local_armour = int(m.group(1))
                is_prop_section = True
            m = RE_EVASION.match(l)
            if m:
                local_evasion = int(m.group(1))
                is_prop_section = True
            m = RE_ENERGY_SHIELD.match(l)
            if m:
                local_energy_shield = int(m.group(1))
                is_prop_section = True
            if any(l.lower().startswith(p) for p in ("quality:", "physical damage:", "critical hit chance:", "attacks per second:", "sockets:")):
                is_prop_section = True

        if is_prop_section:
            continue

        # Modifiers section
        for l in section:
            is_implicit = "(implicit)" in l.lower()
            modifier_lines.append((l, is_implicit))

    # Derive slot and topology
    slot, occupancy, topology = parse_slot_topology_for_base(
        item_class=item_class,
        base_type=base_type,
        target_slot=target_slot,
        target_weapon_set=target_weapon_set,
    )

    # Normalize modifiers
    parsed_mods: list[NormalizedModifier] = []
    for mod_text, is_implicit in modifier_lines:
        parsed_mods.append(normalize_modifier(mod_text, is_implicit=is_implicit, slot=slot))

    # Deterministic hash id
    item_id = f"item_{hashlib.sha256(raw_text.strip().encode('utf-8')).hexdigest()[:12]}"

    return ItemCandidate(
        item_id=item_id,
        name=name,
        base_type=base_type,
        slot=slot,
        slot_occupancy=occupancy,
        slot_conflict_topology=topology,
        rarity=rarity,
        item_level=item_level,
        required_level=req_level,
        required_str=req_str,
        required_dex=req_dex,
        required_int=req_int,
        local_armour=local_armour,
        local_evasion=local_evasion,
        local_energy_shield=local_energy_shield,
        modifiers=parsed_mods,
        raw_text=raw_text.strip(),
        weapon_set=target_weapon_set,
    )
