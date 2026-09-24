"""Modifier normalizer for PoE2 equipment intelligence."""

from __future__ import annotations

import re
from companion.state.provenance import VerificationState
from companion.equipment.mechanics import normalize_mechanic_key
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

RE_LOCAL_ARMOUR_EVA_INC = re.compile(r"^\+?(\d+)%\s+increased\s+Armour\s+and\s+Evasion", re.IGNORECASE)
RE_LOCAL_ARMOUR_EVA_FLAT = re.compile(r"^\+?(\d+)\s+to\s+Armour\s+and\s+Evasion", re.IGNORECASE)

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

RE_MODIFIER_ANNOTATION = re.compile(
    r"^\{\s*(?:(?:Unique|Implicit|Prefix|Suffix|Crafted|Corrupted|Rune|Enchant|Fractured)\s+)?Modifier(?:\b[^}]*)?\s*\}$",
    re.IGNORECASE,
)

RE_UNSCALABLE_VALUE = re.compile(r"^(.*?)\s*[—–-]\s*Unscalable Value\s*$", re.IGNORECASE)
RE_SPECIAL_KEYSTONES = re.compile(
    r"^(Iron Reflexes|Chaos Inoculation|Resolute Technique|Avatar of Fire|Eldritch Battery|Blood Magic|Acrobatics|Arrow Dancing|Ghost Dance|Wind Dancer)$",
    re.IGNORECASE,
)


def is_modifier_annotation(text: str) -> bool:
    """Return True if text is a structural modifier category annotation line (e.g. { Unique Modifier })."""
    return bool(RE_MODIFIER_ANNOTATION.match(text.strip()))


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
) -> NormalizedModifier | None:
    """Classify and normalize a single item modifier line."""
    clean_text = raw_line.strip()
    if is_modifier_annotation(clean_text):
        return None

    # Strip PoE tags like (implicit) or (enchant)
    stripped = re.sub(r"\s*\((implicit|augmented|fractured|enchant)\)", "", clean_text, flags=re.IGNORECASE).strip()

    # Clean roll range annotations like 45(30-50)% -> 45% for pattern matching
    clean_for_match = re.sub(r"(\d+(?:\.\d+)?)\s*\(\s*\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s*\)", r"\1", stripped)

    # Check for conditional trigger/scope first
    is_conditional = bool(RE_CONDITIONAL.search(clean_for_match))

    # Life
    m = RE_LIFE.search(clean_for_match)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.MAXIMUM_LIFE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    # Resistances
    m = RE_FIRE_RES.search(clean_for_match)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.FIRE_RESISTANCE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_COLD_RES.search(clean_for_match)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.COLD_RESISTANCE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_LIGHT_RES.search(clean_for_match)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.LIGHTNING_RESISTANCE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_CHAOS_RES.search(clean_for_match)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.CHAOS_RESISTANCE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    # Attributes
    m = RE_STR.search(clean_for_match)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.STRENGTH,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_DEX.search(clean_for_match)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.DEXTERITY,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_INT.search(clean_for_match)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.INTELLIGENCE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    # Movement Speed
    m = RE_MS.search(clean_for_match)
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

    m = RE_LOCAL_ARMOUR_EVA_INC.search(clean_for_match) or (is_defense_slot and RE_LOCAL_ARMOUR_EVA_FLAT.search(clean_for_match))
    if m and is_defense_slot:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.LOCAL_ARMOUR_AND_EVASION,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.LOCAL_ITEM_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_LOCAL_ARMOUR_INC.search(clean_for_match) or (is_defense_slot and RE_LOCAL_ARMOUR_FLAT.search(clean_for_match))
    if m and is_defense_slot:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.LOCAL_ARMOUR,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.LOCAL_ITEM_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_LOCAL_EVA_INC.search(clean_for_match) or (is_defense_slot and RE_LOCAL_EVA_FLAT.search(clean_for_match))
    if m and is_defense_slot:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.LOCAL_EVASION,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.LOCAL_ITEM_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_LOCAL_ES_INC.search(clean_for_match) or (is_defense_slot and RE_LOCAL_ES_FLAT.search(clean_for_match))
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
        m = RE_LOCAL_PHYS_INC.search(clean_for_match)
        if m:
            return NormalizedModifier(
                modifier_type=NormalizedModifierType.UNKNOWN_MODIFIER,
                scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.LOCAL_ITEM_STAT,
                value=float(m.group(1)),
                raw_text=clean_text,
                is_implicit=is_implicit,
            )

    # Fire damage modifiers
    m = RE_FLAT_FIRE_ATTACK.search(clean_for_match)
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

    m = RE_FLAT_FIRE_SPELL.search(clean_for_match)
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

    m = RE_EXTRA_FIRE.search(clean_for_match)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.EXTRA_FIRE_DAMAGE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.BUILD_MECHANIC,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_INC_FIRE.search(clean_for_match)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.INCREASED_FIRE_DAMAGE,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.GLOBAL_CHARACTER_STAT,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_FIRE_SPELL_LEVEL.search(clean_for_match)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.FIRE_SPELL_LEVEL,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.BUILD_MECHANIC,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    m = RE_ALL_SPELL_LEVEL.search(clean_for_match)
    if m:
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.ALL_SPELL_LEVEL,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.BUILD_MECHANIC,
            value=float(m.group(1)),
            raw_text=clean_text,
            is_implicit=is_implicit,
        )

    # Special mechanics / keystones (e.g. Iron Reflexes — Unscalable Value)
    m = RE_UNSCALABLE_VALUE.match(clean_for_match) or RE_SPECIAL_KEYSTONES.match(clean_for_match)
    if m:
        mech_id = normalize_mechanic_key(clean_for_match)
        return NormalizedModifier(
            modifier_type=NormalizedModifierType.SPECIAL_MECHANIC,
            scope=ModifierScope.CONDITIONAL if is_conditional else ModifierScope.BUILD_MECHANIC,
            value=0.0,
            raw_text=clean_text,
            is_implicit=is_implicit,
            verification_state=VerificationState.UNKNOWN,
            mechanic_id=mech_id,
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
        if is_modifier_annotation(line_s):
            continue
        is_implicit = "(implicit)" in line_s.lower()
        mod = normalize_modifier(line_s, is_implicit=is_implicit, slot=slot)
        if mod is not None:
            results.append(mod)
    return results
