"""Item tooltip parsing and multi-capture stability gate."""

from __future__ import annotations

import re

from companion.gear.hasher import compute_item_hash
from companion.gear.schema import EquippedItem, ItemMod, ItemRarity, ItemSlot, ModType
from companion.state.provenance import VerificationState


def _parse_rarity(text: str) -> ItemRarity:
    m = re.search(r"Rarity:\s*(Normal|Magic|Rare|Unique)", text, flags=re.IGNORECASE)
    if m:
        val = m.group(1).lower()
        if val == "magic":
            return ItemRarity.MAGIC
        if val == "rare":
            return ItemRarity.RARE
        if val == "unique":
            return ItemRarity.UNIQUE
    return ItemRarity.NORMAL


def _parse_int_regex(pattern: str, text: str) -> int:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return 0
    return 0


def parse_item_tooltip(text: str, slot: ItemSlot = ItemSlot.BOOTS) -> EquippedItem:
    """Parse raw tooltip text into structured EquippedItem."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned_lines = [line for line in lines if not re.match(r"^-+$", line)]

    rarity = _parse_rarity(text)

    # Extract level and attribute requirements
    level_req = _parse_int_regex(r"(?:Requires\s+)?Level\s*([0-9]+)", text)
    required_str = _parse_int_regex(r"([0-9]+)\s*Str", text)
    required_dex = _parse_int_regex(r"([0-9]+)\s*Dex", text)
    required_int = _parse_int_regex(r"([0-9]+)\s*Int", text)

    # Sockets
    sockets = 0
    sock_match = re.search(r"Sockets:\s*([A-Za-z\s]+)", text, flags=re.IGNORECASE)
    if sock_match:
        tokens = sock_match.group(1).split()
        sockets = len(tokens)

    # Find name and base type
    name: str | None = None
    base_type = "Unknown Base"

    header_indices = []
    for idx, line in enumerate(cleaned_lines):
        if line.lower().startswith("rarity:"):
            header_indices.append(idx)

    start_idx = 0
    if header_indices:
        start_idx = header_indices[0] + 1

    remaining_lines = cleaned_lines[start_idx:]
    meta_lines = []
    mod_lines = []

    for line in remaining_lines:
        lower = line.lower()
        if (
            lower.startswith("requires")
            or lower.startswith("item level:")
            or lower.startswith("sockets:")
            or "two handed" in lower
            or "one handed" in lower
        ):
            continue

        # Check if line is stat mod
        if (
            line.startswith("+")
            or line.startswith("-")
            or "increased" in lower
            or "reduced" in lower
            or "adds" in lower
            or "%" in lower
        ):
            mod_lines.append(line)
        else:
            if len(meta_lines) < 2:
                meta_lines.append(line)
            else:
                mod_lines.append(line)

    if meta_lines:
        if rarity in (ItemRarity.RARE, ItemRarity.UNIQUE) and len(meta_lines) >= 2:
            name = meta_lines[0]
            base_type = meta_lines[1]
        else:
            name = meta_lines[0]
            base_type = meta_lines[0]

    explicit_mods: list[ItemMod] = []
    for m_line in mod_lines:
        val_match = re.search(r"([+-]?[0-9]+(?:\.[0-9]+)?)", m_line)
        val = float(val_match.group(1)) if val_match else None
        if val is not None and val.is_integer():
            val = int(val)
        explicit_mods.append(
            ItemMod(
                raw_text=m_line,
                mod_type=ModType.EXPLICIT,
                key=None,
                value=val,
            )
        )

    provisional = EquippedItem(
        slot=slot,
        name=name,
        base_type=base_type,
        rarity=rarity,
        level_req=level_req,
        required_str=required_str,
        required_dex=required_dex,
        required_int=required_int,
        explicit_mods=explicit_mods,
        sockets=sockets,
    )
    item_hash = compute_item_hash(provisional)

    return provisional.model_copy(update={"item_hash": item_hash})


def verify_tooltip_stability(
    captures: list[str],
    slot: ItemSlot = ItemSlot.BOOTS,
) -> tuple[EquippedItem | None, VerificationState]:
    """Verify stability across consecutive tooltip text captures."""
    if not captures:
        return None, VerificationState.UNKNOWN

    items = [parse_item_tooltip(c, slot=slot) for c in captures]

    if len(items) == 1:
        single = items[0].model_copy(update={"verification": VerificationState.SINGLE_SOURCE})
        return single, VerificationState.SINGLE_SOURCE

    first_hash = items[0].item_hash
    for it in items[1:]:
        if it.item_hash != first_hash:
            conflict = items[-1].model_copy(update={"verification": VerificationState.CONFLICTING})
            return conflict, VerificationState.CONFLICTING

    verified = items[0].model_copy(update={"verification": VerificationState.VERIFIED})
    return verified, VerificationState.VERIFIED
