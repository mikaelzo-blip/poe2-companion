"""Screen classification for visual frames and extracted OCR text."""

from __future__ import annotations

import re

from companion.vision.schema import ScreenType


def classify_screen(text: str) -> tuple[ScreenType, float]:
    """Classify screen or panel type from recognized landmarks in text."""
    lower = text.lower()

    # Landmark checks for Character Panel
    char_panel_markers = [
        "character",
        "defences",
        "resistances",
        "maximum life",
        "maximum mana",
        "evasion rating",
        "spirit",
    ]
    char_matches = sum(1 for m in char_panel_markers if m in lower)
    if char_matches >= 2:
        confidence = min(0.5 + (char_matches * 0.1), 0.99)
        return ScreenType.CHARACTER_PANEL, confidence

    # Landmark checks for Item Tooltip
    item_markers = [
        "rarity:",
        "item level:",
        "requires level",
        "quality:",
        "attacks per second",
    ]
    item_matches = sum(1 for m in item_markers if m in lower)
    if item_matches >= 2:
        confidence = min(0.5 + (item_matches * 0.12), 0.99)
        return ScreenType.ITEM_TOOLTIP, confidence

    # Landmark checks for Skill Panel
    skill_markers = ["active skills", "support gems", "gem level", "mana cost"]
    skill_matches = sum(1 for m in skill_markers if m in lower)
    if skill_matches >= 2:
        confidence = min(0.5 + (skill_matches * 0.15), 0.95)
        return ScreenType.SKILL_PANEL, confidence

    # Landmark checks for Passive Tree
    passive_markers = ["allocate", "passive skill tree", "refund points", "ascendancy"]
    passive_matches = sum(1 for m in passive_markers if m in lower)
    if passive_matches >= 2:
        confidence = min(0.5 + (passive_matches * 0.15), 0.95)
        return ScreenType.PASSIVE_SCREEN_TARGETED, confidence

    return ScreenType.UNKNOWN, 0.1
