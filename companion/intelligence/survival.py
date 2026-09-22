"""Survival rules evaluation engine for elemental resists, life pools, and chaos resistance."""

from __future__ import annotations

from companion.intelligence.schema import AdvisoryCategory, AdvisoryItem, AdvisorySeverity
from companion.vision.schema import CharacterPanelStats


def evaluate_survival_rules(
    panel_stats: CharacterPanelStats | None,
    character_level: int,
    current_act: int = 1,
) -> list[AdvisoryItem]:
    """Evaluate observed defensive statistics against safety baselines."""
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
            )
        ]

    # 1. Elemental resistance checks
    is_endgame = character_level >= 65 or current_act > 6
    target_cap = 75 if is_endgame else min(75, 20 + current_act * 10)

    res_checks = [
        ("Fire", panel_stats.fire_res, "RES_UNCAPPED_FIRE"),
        ("Cold", panel_stats.cold_res, "RES_UNCAPPED_COLD"),
        ("Lightning", panel_stats.lightning_res, "RES_UNCAPPED_LIGHTNING"),
    ]

    for element, val, code in res_checks:
        if val is not None and val < target_cap:
            deficit = target_cap - val
            severity = AdvisorySeverity.CRITICAL if is_endgame else AdvisorySeverity.WARNING
            advisories.append(
                AdvisoryItem(
                    category=AdvisoryCategory.SURVIVAL,
                    severity=severity,
                    title=f"Uncapped {element} Resistance",
                    description=f"{element} resistance is {val}% (target: {target_cap}%). You are taking increased damage.",
                    recommendation=f"Prioritize +{element} or elemental resistance on rings, amulet, or bench crafts (+{deficit}% needed).",
                    code=code,
                    context={"element": element, "current": val, "target": target_cap, "deficit": deficit},
                )
            )

    # 2. Chaos resistance check
    if is_endgame and panel_stats.chaos_res is not None and panel_stats.chaos_res < -20:
        advisories.append(
            AdvisoryItem(
                category=AdvisoryCategory.SURVIVAL,
                severity=AdvisorySeverity.WARNING,
                title="Dangerous Negative Chaos Resistance",
                description=f"Chaos resistance is {panel_stats.chaos_res}%. Endgame monsters deal substantial chaos damage.",
                recommendation="Equip an Amethyst Ring or craft chaos resistance on open gear suffixes.",
                code="CHAOS_RES_LOW",
                context={"current": panel_stats.chaos_res, "threshold": -20},
            )
        )

    # 3. Life pool check
    if panel_stats.life is not None:
        # Expected life baseline: ~35 life per character level
        expected_life = character_level * 35
        if is_endgame:
            expected_life = max(expected_life, 2500)

        if panel_stats.life < expected_life * 0.5:
            advisories.append(
                AdvisoryItem(
                    category=AdvisoryCategory.SURVIVAL,
                    severity=AdvisorySeverity.CRITICAL,
                    title="Critically Deficient Life Pool",
                    description=f"Current maximum life is {panel_stats.life} (expected at level {character_level}: ~{expected_life}). Extreme one-shot risk.",
                    recommendation="Prioritize +Flat Maximum Life rolls on all armor pieces and jewelry immediately.",
                    code="LIFE_POOL_DEFICIENT",
                    context={"current": panel_stats.life, "expected": expected_life},
                )
            )
        elif panel_stats.life < expected_life * 0.75:
            advisories.append(
                AdvisoryItem(
                    category=AdvisoryCategory.SURVIVAL,
                    severity=AdvisorySeverity.WARNING,
                    title="Low Life Pool",
                    description=f"Current maximum life is {panel_stats.life} (recommended: {expected_life}).",
                    recommendation="Look for gear upgrades with +Maximum Life and passive tree life nodes.",
                    code="LIFE_POOL_LOW",
                    context={"current": panel_stats.life, "expected": expected_life},
                )
            )

    return advisories
