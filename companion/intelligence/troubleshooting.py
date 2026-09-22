"""Troubleshooting rules: mana starvation, attribute bottlenecks, and skill rotation diagnostics."""

from __future__ import annotations

from typing import Mapping
from companion.intelligence.schema import AdvisoryCategory, AdvisoryItem, AdvisorySeverity


def evaluate_troubleshooting_rules(
    character_attributes: Mapping[str, int],
    required_attributes: Mapping[str, int],
    current_mana: int,
    unreserved_mana: int,
    main_skill_cost: int = 0,
) -> list[AdvisoryItem]:
    """Diagnose resource starvation, reservation locks, and attribute requirements."""
    advisories: list[AdvisoryItem] = []

    # 1. Mana reservation lock / starvation
    if main_skill_cost > 0:
        safe_buffer = main_skill_cost * 2
        if unreserved_mana < safe_buffer:
            advisories.append(
                AdvisoryItem(
                    category=AdvisoryCategory.TROUBLESHOOTING,
                    severity=AdvisorySeverity.CRITICAL,
                    title="Mana Starvation / Reservation Lock",
                    description=f"Unreserved mana is {unreserved_mana}, which is less than twice the main skill cost ({main_skill_cost}). Your skill rotation will frequently stall.",
                    recommendation="Reduce mana reservations, obtain mana cost reduction passives/rings, or invest in higher maximum mana.",
                    code="MANA_STARVATION",
                    context={"unreserved_mana": unreserved_mana, "skill_cost": main_skill_cost, "required_buffer": safe_buffer},
                )
            )

    # 2. Attribute bottlenecks
    for attr in ("str", "dex", "int"):
        char_val = character_attributes.get(attr, 0)
        req_val = required_attributes.get(attr, 0)
        if req_val > 0:
            if char_val < req_val:
                deficit = req_val - char_val
                advisories.append(
                    AdvisoryItem(
                        category=AdvisoryCategory.TROUBLESHOOTING,
                        severity=AdvisorySeverity.CRITICAL,
                        title=f"Attribute Deficit: {attr.upper()}",
                        description=f"Current {attr.upper()} is {char_val}, but equipped gear or gem setup requires {req_val} ({deficit} deficit).",
                        recommendation=f"Socket an attribute node, craft +{attr.upper()} onto jewelry, or equip an attribute amulet.",
                        code=f"ATTRIBUTE_DEFICIT_{attr.upper()}",
                        context={"attribute": attr, "current": char_val, "required": req_val, "deficit": deficit},
                    )
                )
            elif char_val - req_val < 5:
                margin = char_val - req_val
                advisories.append(
                    AdvisoryItem(
                        category=AdvisoryCategory.TROUBLESHOOTING,
                        severity=AdvisorySeverity.WARNING,
                        title=f"Tight Attribute Margin: {attr.upper()}",
                        description=f"{attr.upper()} margin is only +{margin} above gear requirement ({char_val}/{req_val}).",
                        recommendation=f"Be cautious when replacing gear pieces providing {attr.upper()} to avoid disabling active gems.",
                        code=f"ATTRIBUTE_TIGHT_{attr.upper()}",
                        context={"attribute": attr, "current": char_val, "required": req_val, "margin": margin},
                    )
                )

    return advisories
