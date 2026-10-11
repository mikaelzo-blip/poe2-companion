"""Guide-driven safety gate: breaker rules and weapons the guide never uses."""
from __future__ import annotations

import re

from companion.builds.guide import GuideProfile

# Singular weapon class labels (guides' vocabulary); anything else is not a weapon.
WEAPON_CLASSES = frozenset({
    "Staff", "Quarterstaff", "Crossbow", "Bow", "Wand", "Sceptre", "Focus", "Shield",
    "Buckler", "Quiver", "Spear", "Flail", "Talisman", "One Hand Mace", "Two Hand Mace",
})


def breaker_reasons(
    mod_lines: list[str], profile: GuideProfile | None, level: int | None, slot: str
) -> list[str]:
    if profile is None:
        return []
    return [
        r.reason
        for r in profile.breaker_rules
        if (level is None or level >= r.from_level)
        and slot not in r.exclude_slots
        and any(re.search(r.pattern, line, re.IGNORECASE) for line in mod_lines)
    ]


def weapon_not_in_guide(item_class: str, profile: GuideProfile | None) -> str | None:
    if profile is None or item_class not in WEAPON_CLASSES:
        return None
    used = {c for st in profile.stages for cs in st.weapon_classes.values() for c in cs}
    if not used or item_class in used:
        return None
    return f"Senjata tidak dipakai guide ({item_class})"
