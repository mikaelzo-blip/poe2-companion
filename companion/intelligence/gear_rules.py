"""Gear optimization rules: open crafts, socket gaps, and base tier obsolescence."""

from __future__ import annotations

from companion.gear.schema import GearAuditState, ItemRarity, ItemSlot
from companion.intelligence.schema import AdvisoryCategory, AdvisoryItem, AdvisorySeverity


def evaluate_gear_rules(gear_state: GearAuditState, character_level: int) -> list[AdvisoryItem]:
    """Inspect equipped items for craft potential, obsolete bases, or missing gear."""
    advisories: list[AdvisoryItem] = []

    for slot, item in gear_state.slots.items():
        # 1. Open craft detection for rare items with < 6 affixes
        if item.rarity == ItemRarity.RARE:
            total_affixes = len(item.implicit_mods) + len(item.explicit_mods)
            has_crafted = any("crafted" in mod.raw_text.lower() for mod in item.explicit_mods)
            if total_affixes < 6 and not has_crafted:
                advisories.append(
                    AdvisoryItem(
                        category=AdvisoryCategory.GEAR,
                        severity=AdvisorySeverity.INFO,
                        title=f"Open Craft Slot: {slot.value.title()}",
                        description=f"{item.name or item.base_type} has only {total_affixes} affixes and lacks bench crafted mods.",
                        recommendation="Visit the crafting bench to add a needed resistance, attribute, or defensive prefix/suffix.",
                        code="GEAR_OPEN_CRAFT",
                        context={"slot": slot.value, "item": item.name or item.base_type, "affixes": total_affixes},
                    )
                )

        # 2. Outdated base tier detection
        if character_level >= 45 and item.item_level and item.item_level > 0:
            level_diff = character_level - item.item_level
            if level_diff > 20:
                advisories.append(
                    AdvisoryItem(
                        category=AdvisoryCategory.GEAR,
                        severity=AdvisorySeverity.WARNING,
                        title=f"Outdated Base: {slot.value.title()}",
                        description=f"{item.base_type} (iLvl {item.item_level}) is {level_diff} levels behind character level {character_level}.",
                        recommendation=f"Upgrade your {slot.value} base to an appropriate level {character_level} base to gain higher armor, evasion, energy shield, or weapon base damage.",
                        code="GEAR_BASE_OUTDATED",
                        context={"slot": slot.value, "item_level": item.item_level, "char_level": character_level},
                    )
                )

    return advisories
