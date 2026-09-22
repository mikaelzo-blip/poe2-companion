"""Deterministic item hashing for identity and deduplication."""

from __future__ import annotations

import hashlib
import json

from companion.gear.schema import EquippedItem


def compute_item_hash(item: EquippedItem) -> str:
    """Compute deterministic SHA-256 hash string for an item."""
    canonical_components = {
        "slot": item.slot.value,
        "name": (item.name or "").strip().lower(),
        "base_type": item.base_type.strip().lower(),
        "rarity": item.rarity.value,
        "level_req": item.level_req,
        "required_str": item.required_str,
        "required_dex": item.required_dex,
        "required_int": item.required_int,
        "implicit_mods": sorted([m.raw_text.strip().lower() for m in item.implicit_mods]),
        "explicit_mods": sorted([m.raw_text.strip().lower() for m in item.explicit_mods]),
        "runes": sorted([r.strip().lower() for r in item.runes]),
        "sockets": item.sockets,
    }

    serialized = json.dumps(canonical_components, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
