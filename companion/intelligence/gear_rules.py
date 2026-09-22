"""Gear optimization rules and slot audit diagnostics."""

from __future__ import annotations

from companion.gear.schema import GearAuditState
from companion.intelligence.schema import AdvisoryItem


def evaluate_gear_rules(gear_state: GearAuditState, character_level: int) -> list[AdvisoryItem]:
    """Inspect equipped items for verified gear issues.

    Invented rare affix count (< 6) and arbitrary base item level gap (> 20)
    heuristics have been removed per the M9 provenance policy.
    """
    advisories: list[AdvisoryItem] = []
    return advisories
