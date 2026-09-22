"""Survival rules evaluation engine for endgame resistance caps."""

from __future__ import annotations

from companion.intelligence.schema import (
    AdvisoryCategory,
    AdvisoryItem,
    AdvisorySeverity,
    ProvenanceCategory,
)
from companion.vision.schema import CharacterPanelStats


def evaluate_survival_rules(
    panel_stats: CharacterPanelStats | None,
    character_level: int,
    current_act: int = 1,
) -> list[AdvisoryItem]:
    """Evaluate observed defensive statistics against verified endgame baselines.

    Pruned of invented act scaling curves, negative chaos thresholds, and fabricated
    life pool scaling formulas. The 75% endgame elemental resistance cap is retained
    as a labeled inference (is_inference=True).
    """
    advisories: list[AdvisoryItem] = []

    if panel_stats is None:
        return [
            AdvisoryItem(
                category=AdvisoryCategory.SURVIVAL,
                severity=AdvisorySeverity.INFO,
                title="Missing Defensive Stats",
                description="No defensive stats have been observed yet via Character Panel parse.",
                recommendation="Capture the in-game character defensive panel (`C` key) to verify resistance caps and life pool.",
                code="SURVIVAL_STATS_UNOBSERVED",
                is_inference=False,
                provenance=ProvenanceCategory.SOURCE_BACKED,
            )
        ]

    # Only evaluate the 75% cap for endgame (character level >= 65 or current_act > 6)
    is_endgame = character_level >= 65 or current_act > 6
    if not is_endgame:
        return advisories

    target_cap = 75
    res_checks = [
        ("Fire", panel_stats.fire_res, "RES_UNCAPPED_FIRE"),
        ("Cold", panel_stats.cold_res, "RES_UNCAPPED_COLD"),
        ("Lightning", panel_stats.lightning_res, "RES_UNCAPPED_LIGHTNING"),
    ]

    for element, val, code in res_checks:
        if val is not None and val < target_cap:
            deficit = target_cap - val
            advisories.append(
                AdvisoryItem(
                    category=AdvisoryCategory.SURVIVAL,
                    severity=AdvisorySeverity.WARNING,
                    title=f"Uncapped {element} Resistance",
                    description=f"{element} resistance is {val}% (endgame target: {target_cap}%). You are taking increased damage.",
                    recommendation=f"Prioritize +{element} or elemental resistance on rings, amulet, or bench crafts (+{deficit}% needed).",
                    code=code,
                    context={"element": element, "current": val, "target": target_cap, "deficit": deficit},
                    is_inference=True,
                    provenance=ProvenanceCategory.LABELED_INFERENCE,
                )
            )

    return advisories
