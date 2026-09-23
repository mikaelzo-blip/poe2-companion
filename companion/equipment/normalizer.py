"""Modifier normalizer for PoE2 equipment intelligence."""

from __future__ import annotations

import re
from companion.state.provenance import VerificationState
from companion.equipment.schema import (
    ModifierScope,
    NormalizedModifier,
    NormalizedModifierType,
    SlotType,
)

RE_LIFE = re.compile(r"^\+?(\d+)\s+to\s+maximum\s+Life", re.IGNORECASE)
RE_FIRE_RES = re.compile(r"^\+?(\d+)%\s+to\s+Fire\s+Resistance", re.IGNORECASE)
RE_COLD_RES = re.compile(r"^\+?(\d+)%\s+to\s+Cold\s+Resistance", re.IGNORECASE)
RE_LIGHT_RES = re.compile(r"^\+?(\d+)%\s+to\s+Lightning\s+Resistance", re.IGNORECASE)
RE_CHAOS_RES = re.compile(r"^\+?(\d+)%\s+to\s+Chaos\s+Resistance", re.IGNORECASE)
RE_ALL_RES = re.compile(r"^\+?(\d+)%\s+to\s+all\s+Elemental\s+Resistances", re.IGNORECASE)

RE_STR = re.compile(r"^\+?(\d+)\s+to\s+Strength", re.IGNORECASE)
RE_DEX = re.compile(r"^\+?(\d+)\s+to\s+Dexterity", re.IGNORECASE)
RE_INT = re.compile(r"^\+?(\d+)\s+to\s+Intelligence", re.IGNORECASE)
RE_ALL_ATTR = re.compile(r"^\+?(\d+)\s+to\s+all\s+Attributes", re.IGNORECASE)

RE_MS = re.compile(r"^\+?(\d+)%\s+increased\s+Movement\s+Speed", re.IGNORECASE)

RE_LOCAL_ARMOUR_INC = re.compile(r"^\+?(\d+)%\s+increased\s+Armour", re.IGNORECASE)
RE_LOCAL_ARMOUR_FLAT = re.compile(r"^\+?(\d+)\s+to\s+Armour", re.IGNORECASE)
RE_LOCAL_EVA_INC = re.compile(r"^\+?(\d+)%\s+increased\s+Evasion(\s+Rating)?", re.IGNORECASE)
RE_LOCAL_EVA_FLAT = re.compile(r"^\+?(\d+)\s+to\s+Evasion(\s+Rating)?", re.IGNORECASE)
RE_LOCAL_ES_INC = re.compile(r"^\+?(\d+)%\s+increased\s+Energy\s+Shield", re.IGNORECASE)
RE_LOCAL_ES_FLAT = re.compile(r"^\+?(\d+)\s+to\s+Energy\s+Shield", re.IGNORECASE)

RE_LOCAL_PHYS_INC = re.compile(r"^\+?(\d+)%\s+increased\s+Physical\s+Damage", re.IGNORECASE)

RE_FLAT_FIRE_ATTACK = re.compile(
    r"^Adds\s+(\d+)\s+to\s+(\d+)\s+Fire\s+Damage\s+to\s+Attacks", re.IGNORECASE
)
RE_FLAT_FIRE_SPELL = re.compile(
    r"^Adds\s+(\d+)\s+to\s+(\d+)\s+Fire\s+Damage\s+to\s+Spells", re.IGNORECASE
)
RE_EXTRA_FIRE = re.compile(
    r"^Gain\s+(\d+)%\s+of\s+Physical\s+Damage\s+as\s+Extra\s+Fire\s+Damage", re.IGNORECASE
)
RE_INC_FIRE = re.compile(r"^(\d+)%\s+increased\s+Fire\s+Damage", re.IGNORECASE)
RE_FIRE_SPELL_LEVEL = re.compile(
    r"^\+?(\d+)\s+to\s+Level\s+of\s+all\s+Fire\s+Spell\s+Skill\s+Gems", re.IGNORECASE
)
RE_ALL_SPELL_LEVEL = re.compile(
    r"^\+?(\d+)\s+to\s+Level\s+of\s+all\s+Spell\s+Skill\s+Gems", re.IGNORECASE
)

RE_CONDITIONAL = re.compile(
    r"\b(during|while|recently|if\s+you('ve)?|when|on\s+kill|against\s+blinded)\b",
    re.IGNORECASE,
)

DEFENSE_SLOTS = {
    SlotType.HELMET,
    SlotType.BODY_ARMOUR,
    SlotType.GLOVES,
    SlotType.BOOTS,
    SlotType.OFF_HAND,
}

WEAPON_SLOTS = {
    SlotType.MAIN_HAND,
    SlotType.OFF_HAND,
}


def normalize_modifier(
    raw_line: str,
    is_implicit: bool = False,
    slot: SlotType | None = None,
) -> NormalizedModifier:
    """Classify and normalize a single item modifier line."""
    clean_text = raw_line.strip()
    # Strip PoE tags like (implicit) or (enchant)
    stripped = re.sub(r"\s*\((implicit|augmented|fractured|enchant)\)", "", clean_text, flags=re.IGNORECASE).strip()

    # Check for conditional trigger/scope first
    is_conditional = bool(RE_CONDITIONAL.search(stripped))

    # Life
    m = RE_LIFE.search(stripped)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.MAXIMUM_LIFE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    # Resistances
    m = RE_FIRE_RES.search(stripped)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.FIRE_RESISTANCE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_COLD_RES.search(stripped)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.COLD_RESISTANCE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_LIGHT_RES.search(stripped)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.LIGHTNING_RESISTANCE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_CHAOS_RES.search(stripped)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.CHAOS_RESISTANCE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    # Attributes
    m = RE_STR.search(stripped)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.STRENGTH,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_DEX.search(stripped)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.DEXTERITY,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_INT.search(stripped)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.INTELLIGENCE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    # Movement Speed
    m = RE_MS.search(stripped)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.MOVEMENT_SPEED,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    # Local Defenses on Defense Slots
    is_defense_slot = slot in DEFENSE_SLOTS if slot else True

    m = RE_LOCAL_ARMOUR_INC.search(stripped) or (is_defense_slot and RE_LOCAL_ARMOUR_FLAT.search(stripped))
    if m and is_defense_slot:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.LOCAL_ARMOUR,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.LOCAL_ITEM_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_LOCAL_EVA_INC.search(stripped) or (is_defense_slot and RE_LOCAL_EVA_FLAT.search(stripped))
    if m and is_defense_slot:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.LOCAL_EVASION,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.LOCAL_ITEM_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_LOCAL_ES_INC.search(stripped) or (is_defense_slot and RE_LOCAL_ES_FLAT.search(stripped))
    if m and is_defense_slot:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.LOCAL_ENERGY_SHIELD,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.LOCAL_ITEM_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    # Weapon physical damage
    if slot in WEAPON_SLOTS:
        m = RE_LOCAL_PHYS_INC.search(stripped)
        if m:
            return NormalizedModifier(
                modifier_type=NormalizedModifierType.UNKNOWN_MODIFIER,
                scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.LOCAL_ITEM_STAT,
                value=float(m.group(1)),
                raw_text=clean_text,
                is_implicit=is_implicit,
            )

    # Fire damage modifiers
    m = RE_FLAT_FIRE_ATTACK.search(stripped)
    if m:
        low, high = float(m.group(1)), float(m.group(2))
        avg = (low + high) / 2.0
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.FLAT_FIRE_DAMAGE_ATTACK,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.BUILD_MECHANIC,
            value=avg,
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_FLAT_FIRE_SPELL.search(stripped)
    if m:
        low, high = float(m.group(1)), float(m.group(2))
        avg = (low + high) / 2.0
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.FLAT_FIRE_DAMAGE_SPELL,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.BUILD_MECHANIC,
            value=avg,
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_EXTRA_FIRE.search(stripped)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.EXTRA_FIRE_DAMAGE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.BUILD_MECHANIC,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_INC_FIRE.search(stripped)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.INCREASED_FIRE_DAMAGE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_FIRE_SPELL_LEVEL.search(stripped)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.FIRE_SPELL_LEVEL,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.BUILD_MECHANIC,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_ALL_SPELL_LEVEL.search(stripped)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.ALL_SPELL_LEVEL,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.BUILD_MECHANIC,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    # Conditional modifier with unmodeled type
    if is_conditional:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.UNKNOWN_MODIFIER,
            scope=ModifierScope.CONDITIONAL,
            value=0.0,
            raw_text=clean_text,
            is_implicit=is_implicit,
            verification_state=VerificationState.UNKNOWN,
        )

    # Unknown modifier
    return NormalizedModifier(
        modifier_type=NormalizedModifierType.UNKNOWN_MODIFIER,
        scope=ModifierScope.UNKNOWN_SCOPE,
        value=0.0,
        raw_text=clean_text,
        is_implicit=is_implicit,
        verification_state=VerificationState.UNKNOWN,
    )


def normalize_modifier_text(lines: list[str], slot: SlotType | None = None) -> list[NormalizedModifier]:
    """Normalize a list of modifier lines."""
    results: list[NormalizedModifier] = []
    for line in lines:
        line_s = line.strip()
        if not line_s or line_s.startswith("---") or line_s.startswith("Item Class") or line_s.startswith("Rarity"):
            continue
        is_implicit = "(implicit)" in line_s.lower()
        results.append(normalize_modifier(line_s, is_implicit=is_implicit, slot=slot))
    return results
