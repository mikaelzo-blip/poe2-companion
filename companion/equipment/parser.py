"""PoE2 item text parser for manual clipboard ingestion and candidate evaluation."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from companion.equipment.normalizer import is_modifier_annotation, normalize_modifier
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

RE_REQ_LEVEL = re.compile(r"(?:Level|Lvl)[:\s]+(\d+)", re.IGNORECASE)
RE_REQ_STR = re.compile(r"(?:Str(?:ength)?[:\s]+(\d+)|(\d+)\s+Str(?:ength)?)", re.IGNORECASE)
RE_REQ_DEX = re.compile(r"(?:Dex(?:terity)?[:\s]+(\d+)|(\d+)\s+Dex(?:terity)?)", re.IGNORECASE)
RE_REQ_INT = re.compile(r"(?:Int(?:elligence)?[:\s]+(\d+)|(\d+)\s+Int(?:elligence)?)", re.IGNORECASE)

RE_MODIFIER_HINT = re.compile(
    r"(\d+%|\b(?:increased|reduced|more|less|to maximum|resistance|damage|gem|socketed|adds|gain|per second|leech|unscalable|requires)\b|^\+?\d+)",
    re.IGNORECASE,
)


class InvalidItemClipboardError(ValueError):
    """Raised when clipboard or input text does not contain recognizable PoE2 item structure."""
    pass


VALID_ITEM_RARITIES = {"normal", "magic", "rare", "unique"}


def validate_poe2_item_envelope(raw_text: str) -> None:
    """Validate that raw_text conforms to the standard PoE2 item clipboard envelope.

    In PoE2, an item copied from the game begins with an Item Class line,
    a Rarity line, and the item name and/or base type before section separators.

    Raises:
        InvalidItemClipboardError: If text is empty or does not contain recognizable
            PoE2 item structure.
    """
    if not raw_text or not raw_text.strip():
        raise InvalidItemClipboardError("Clipboard does not contain recognizable PoE2 item text.")

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if len(lines) < 3:
        raise InvalidItemClipboardError("Clipboard does not contain recognizable PoE2 item text.")

    # Check the header block (lines before the first separator)
    header_lines: list[str] = []
    for line in lines:
        if line.startswith("---") or line.startswith("==="):
            break
        header_lines.append(line)

    if not header_lines:
        raise InvalidItemClipboardError("Clipboard does not contain recognizable PoE2 item text.")

    item_class: str | None = None
    rarity: str | None = None
    rem_names: list[str] = []

    for line in header_lines:
        m_cls = RE_ITEM_CLASS.match(line)
        if m_cls:
            item_class = m_cls.group(1).strip()
            continue
        m_rar = RE_RARITY.match(line)
        if m_rar:
            rarity = m_rar.group(1).strip().lower()
            continue
        rem_names.append(line)

    # Both Item Class and Rarity are mandatory for a valid PoE2 item clipboard
    if not item_class:
        raise InvalidItemClipboardError("Clipboard does not contain recognizable PoE2 item text.")

    if not rarity or rarity not in VALID_ITEM_RARITIES:
        raise InvalidItemClipboardError("Clipboard does not contain recognizable PoE2 item text.")

    # Must have at least one name / base_type line in the header
    if not rem_names:
        raise InvalidItemClipboardError("Clipboard does not contain recognizable PoE2 item text.")


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

    # Shields and Foci (Off Hand)
    if (
        "shield" in cls_lower
        or "shield" in base_lower
        or "buckler" in base_lower
        or "focus" in cls_lower
        or "foci" in cls_lower
        or "focus" in base_lower
    ):
        slot = SlotType.OFF_HAND
        return slot, SlotOccupancy.OFF_HAND, SlotConflictTopology(
            occupied_slots=[SlotType.OFF_HAND],
            conflicting_slots=[SlotType.OFF_HAND],
            allowed_companion_slots=[],
            is_known=True,
        )

    # Two Hand Melee Weapons (Two Hand Swords, Two Hand Maces, Two Hand Axes)
    if "two hand" in cls_lower or "two-hand" in cls_lower:
        slot = SlotType.MAIN_HAND
        return slot, SlotOccupancy.TWO_HAND, SlotConflictTopology(
            occupied_slots=[SlotType.MAIN_HAND, SlotType.OFF_HAND],
            conflicting_slots=[SlotType.MAIN_HAND, SlotType.OFF_HAND],
            allowed_companion_slots=[],
            is_known=True,
        )

    # One Hand Weapons (Wands, Sceptres, Daggers, Swords, Maces, Flails, Axes)
    if any(k in cls_lower or k in base_lower for k in ("wand", "sceptre", "dagger", "sword", "mace", "flail", "axe")):
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
    target_weapon_set: WeaponSetContext | str | None = None,
) -> ItemCandidate:
    """Parse standard PoE2 item clipboard text into ItemCandidate."""
    validate_poe2_item_envelope(raw_text)

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

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
    annotations: list[str] = []
    flavor_text: str | None = None

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
        if first_line.lower().startswith("requirements:") or first_line.lower().startswith("requires:"):
            for rline in section:
                m = RE_REQ_LEVEL.search(rline)
                if m:
                    req_level = int(m.group(1))
                m = RE_REQ_STR.search(rline)
                if m:
                    req_str = int(m.group(1) or m.group(2))
                m = RE_REQ_DEX.search(rline)
                if m:
                    req_dex = int(m.group(1) or m.group(2))
                m = RE_REQ_INT.search(rline)
                if m:
                    req_int = int(m.group(1) or m.group(2))
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

        # Status tags section (Corrupted, Mirrored, Unmodifiable)
        if all(l.strip() in ("Corrupted", "Mirrored", "Unmodifiable") for l in section):
            continue

        # Flavor text section (Unique items, trailing section without modifier syntax)
        if rarity == "unique" and not any(is_modifier_annotation(l) for l in section):
            if not any(RE_MODIFIER_HINT.search(l) for l in section):
                flavor_text = "\n".join(section)
                continue

        # Modifiers section
        for l in section:
            if is_modifier_annotation(l):
                annotations.append(l)
                continue
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
        mod = normalize_modifier(mod_text, is_implicit=is_implicit, slot=slot)
        if mod is not None:
            parsed_mods.append(mod)

    # Deterministic hash id
    item_id = f"item_{hashlib.sha256(raw_text.strip().encode('utf-8')).hexdigest()[:12]}"

    wset_enum = (
        WeaponSetContext.from_val(target_weapon_set)
        if target_weapon_set is not None
        else None
    )

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
        annotations=annotations,
        flavor_text=flavor_text,
        raw_text=raw_text.strip(),
        weapon_set=wset_enum,
    )
