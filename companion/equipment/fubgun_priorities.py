"""Verified campaign gear priorities and materiality from Fubgun 0.5.5 guide.

PROVENANCE:
Primary Source: Fubgun 0.5.5 Flameblast / Oil Grenade Mobalytics guide.
Target build progression: Campaign leveling (lvl 1-14, lvl 15-32, lvl 33-51, lvl 52 Swap, lvl 53-68)
"""

from __future__ import annotations

import re
from typing import Any

from companion.equipment.rules import BuildProgressionStage
from companion.equipment.schema import SlotType

FUBGUN_GUIDE_PROVENANCE = "Fubgun 0.5.5 Flameblast / Oil Grenade Mobalytics guide"

# Non-material modifiers on campaign gear that must NOT block recommendations
RE_CAMPAIGN_NON_MATERIAL = re.compile(
    r"\b("
    r"maximum\s+mana|mana\b|"
    r"regenerat[a-z]*(\s+per\s+second|\s+rate)?|"
    r"item\s+rarity|"
    r"light\s+radius|"
    r"accuracy\s+rating|accuracy\b|"
    r"stun\s+threshold|ailment\s+threshold|"
    r"stun\s+and\s+ailment\s+threshold"
    r")\b",
    re.IGNORECASE,
)

# Genuinely material effects that must be preserved conservatively even if they mention words above
RE_GENUINELY_MATERIAL = re.compile(
    r"\b("
    r"damage|adds?\b.*\bto\b|critical|strike[a-z]*|penetrat[a-z]*|multiplier[a-z]*|"
    r"applies?\s+to|taken\s+as|damage\s+taken|suppress[a-z]*|block[a-z]*|deflect[a-z]*|ward|"
    r"maximum\s+.*resistan[a-z]*|intimidate|onslaught|unholy\s+might|consecrat[a-z]*|"
    r"curse[a-z]*|blind[a-z]*|taunt[a-z]*|exposure|wither|gem[a-z]*|socketed|reserv[a-z]*|"
    r"cooldown[a-z]*|aura[a-z]*|iron\s+reflexes"
    r")\b",
    re.IGNORECASE,
)


def is_fubgun_non_material_modifier(
    mod_text: str,
    slot: SlotType | None = None,
    stage: BuildProgressionStage | None = None,
) -> bool:
    """Return True if an unsupported modifier is non-material under Fubgun campaign priorities."""
    if stage is not None and not stage.is_campaign:
        return False

    clean = mod_text.strip().lower()

    # If it contains genuinely material combat/keystone/defense mechanics, it is material!
    if RE_GENUINELY_MATERIAL.search(clean):
        # Unless it is simply stun/ailment threshold
        if not ("stun threshold" in clean or "ailment threshold" in clean or "accuracy" in clean):
            return False

    # Check non-material patterns
    if RE_CAMPAIGN_NON_MATERIAL.search(clean):
        return True

    return False


def get_fubgun_slot_priority_note(
    slot: SlotType,
    stage: BuildProgressionStage | None = None,
) -> str:
    """Return short guide priority note for the specified gear slot and progression stage."""
    stage_name = stage.value if stage else "campaign"

    if slot == SlotType.BOOTS:
        return "Fubgun — Movement Speed is critical on Boots (mandatory priority, then Resistance/Life)."

    if slot == SlotType.HELMET:
        return f"Fubgun {stage_name} — Resistance > Life (local defenses are secondary tie-breakers)."

    if slot == SlotType.BODY_ARMOUR:
        return "Fubgun — High Armour or Armour/Evasion hybrid is primary defense priority; Life + Resistance remain valuable."

    if slot in (SlotType.RING_1, SlotType.RING_2, SlotType.GLOVES):
        return "Fubgun campaign — Resistance/Life; flat damage to attacks is a meaningful offensive priority during leveling."

    if slot in (SlotType.AMULET, SlotType.BELT):
        return "Fubgun campaign — Generic Resistance/Life; attributes only according to actual requirements."

    if slot in (SlotType.MAIN_HAND, SlotType.OFF_HAND):
        if stage == BuildProgressionStage.LEVELING_15_32:
            return "Fubgun lvl15-32 — Highest damage Crossbow (Varnished Crossbow benchmark); % Physical desirable, Attack Speed is not a major value."
        if stage and stage.is_pre_swap:
            return "Fubgun pre-swap — Highest damage Crossbow; % Physical desirable."
        return "Fubgun post-swap — Set 1 Flameblast staff, Set 2 Oil Grenade crossbow."

    return f"Build priority: Fubgun {stage_name} — Resistance > Life"


def get_fubgun_build_priority_short(stage: BuildProgressionStage | None = None) -> str:
    """Return concise one-line build priority header."""
    if stage == BuildProgressionStage.LEVELING_15_32:
        return "Fubgun lvl15-32 — Resistance > Life"
    if stage and stage.is_pre_swap:
        return f"Fubgun {stage.value} — Resistance > Life"
    return "Fubgun campaign — Resistance > Life"
