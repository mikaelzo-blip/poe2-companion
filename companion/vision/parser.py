"""Character panel text extraction and multi-capture verification logic."""

from __future__ import annotations

import re

from companion.state.provenance import VerificationState
from companion.vision.schema import CharacterPanelStats


def _extract_int_field(patterns: list[str], text: str) -> int | None:
    """Try matching regex patterns and return first matched integer."""
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            val_str = m.group(1).replace(",", "")
            try:
                return int(val_str)
            except ValueError:
                continue
    return None


def parse_character_panel(text: str) -> CharacterPanelStats:
    """Parse defensive attributes and resistances from character panel text."""
    life = _extract_int_field(
        [
            r"(?:Maximum\s+)?Life:\s*([0-9,]+)",
            r"Life\s+([0-9,]+)\s*/\s*[0-9,]+",
        ],
        text,
    )
    mana = _extract_int_field(
        [
            r"(?:Maximum\s+)?Mana:\s*([0-9,]+)",
            r"Mana\s+([0-9,]+)\s*/\s*[0-9,]+",
        ],
        text,
    )
    spirit = _extract_int_field(
        [
            r"Spirit:\s*([0-9,]+)",
            r"Spirit\s+([0-9,]+)\s*/\s*[0-9,]+",
        ],
        text,
    )
    armour = _extract_int_field(
        [
            r"Armour:\s*([0-9,]+)",
            r"Armour\s+([0-9,]+)",
        ],
        text,
    )
    evasion = _extract_int_field(
        [
            r"Evasion(?:\s+Rating)?:\s*([0-9,]+)",
            r"Evasion\s+([0-9,]+)",
        ],
        text,
    )
    fire_res = _extract_int_field(
        [
            r"Fire\s+Resistance:\s*([+-]?[0-9]+)%",
            r"Fire\s+Res:\s*([+-]?[0-9]+)%",
        ],
        text,
    )
    cold_res = _extract_int_field(
        [
            r"Cold\s+Resistance:\s*([+-]?[0-9]+)%",
            r"Cold\s+Res:\s*([+-]?[0-9]+)%",
        ],
        text,
    )
    lightning_res = _extract_int_field(
        [
            r"Lightning\s+Resistance:\s*([+-]?[0-9]+)%",
            r"Lightning\s+Res:\s*([+-]?[0-9]+)%",
        ],
        text,
    )
    chaos_res = _extract_int_field(
        [
            r"Chaos\s+Resistance:\s*([+-]?[0-9]+)%",
            r"Chaos\s+Res:\s*([+-]?[0-9]+)%",
        ],
        text,
    )

    return CharacterPanelStats(
        life=life,
        mana=mana,
        spirit=spirit,
        armour=armour,
        evasion=evasion,
        fire_res=fire_res,
        cold_res=cold_res,
        lightning_res=lightning_res,
        chaos_res=chaos_res,
    )


def evaluate_verification_state(
    captures: list[CharacterPanelStats],
) -> tuple[CharacterPanelStats | None, VerificationState]:
    """Evaluate semantic verification state across consecutive visual captures."""
    if not captures:
        return None, VerificationState.UNKNOWN

    if len(captures) == 1:
        return captures[0], VerificationState.SINGLE_SOURCE

    # If 2 or more captures exist, compare first against all subsequent
    first = captures[0]
    for c in captures[1:]:
        if c != first:
            return captures[-1], VerificationState.CONFLICTING

    return first, VerificationState.VERIFIED
