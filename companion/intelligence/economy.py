"""Economy advice and upgrade prioritization engine based on ROI principles."""

from __future__ import annotations

from companion.intelligence.schema import EconomyPriority


def evaluate_economy_priorities(
    character_level: int,
    current_resists_capped: bool,
    weapon_dps_lagging: bool,
    available_currency_tier: str = "low",
) -> list[EconomyPriority]:
    """Calculate deterministic upgrade priority ladder based on defensive caps and DPS."""
    priorities: list[EconomyPriority] = []

    # 1. Defenses first: uncapped resistances have infinite defensive ROI
    if not current_resists_capped:
        priorities.append(
            EconomyPriority(
                priority_tier=1,
                target_slot="Rings / Amulet / Bench Craft",
                recommended_action="Cap elemental resistances (75%) via crafting bench or cheap two-stone/amethyst rings",
                estimated_cost="1-5 Regal / Alchemy or Crafting bench gold",
                roi_reason="Resistance cap provides highest defensive survival return per currency spent; uncapped damage increases mortality exponentially.",
            )
        )

    # 2. Offensive scaling: weapon DPS upgrade when resists are secure
    if weapon_dps_lagging:
        tier = 1 if current_resists_capped else 2
        priorities.append(
            EconomyPriority(
                priority_tier=tier,
                target_slot="Main Weapon",
                recommended_action=f"Acquire high base DPS weapon appropriate for level {character_level} and apply flat physical/elemental essences",
                estimated_cost="5-15 Chaos Orbs or Essences",
                roi_reason="Weapon base damage directly multiplies entire skill scaling tree, significantly accelerating clear speed and zone safety.",
            )
        )

    # 3. Gem links and utility
    priorities.append(
        EconomyPriority(
            priority_tier=2 if current_resists_capped and not weapon_dps_lagging else 3,
            target_slot="Body Armour / Skill Gems",
            recommended_action="Secure 4-link or 5-link primary skill setup with complementary support gems",
            estimated_cost="10-25 Chaos Orbs / Jeweller's Orbs",
            roi_reason="Additional support gems provide 30-40% more damage multiplier per link.",
        )
    )

    # 4. High-end endgame investments
    if character_level >= 65:
        priorities.append(
            EconomyPriority(
                priority_tier=3,
                target_slot="Jewels / Endgame Uniques",
                recommended_action="Invest in specific unique items or build-enabling passive jewels",
                estimated_cost="50+ Chaos Orbs / Exalted Orbs",
                roi_reason="Refines high-end variant synergies once core defensive baselines and weapon foundations are established.",
            )
        )

    return sorted(priorities, key=lambda p: p.priority_tier)
