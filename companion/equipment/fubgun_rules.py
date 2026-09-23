"""Verified stage-aware rules for Fubgun Flameblast / Oil Grenade build."""

from __future__ import annotations

from companion.equipment.rules import (
    BuildBreakerCertainty,
    BuildProgressionStage,
    RuleSeverity,
)
from companion.equipment.schema import (
    ModifierScope,
    NormalizedModifier,
    NormalizedModifierType,
    SlotType,
    WeaponSetContext,
)


def evaluate_fubgun_modifier(
    mod: NormalizedModifier,
    slot: SlotType,
    weapon_set: WeaponSetContext | None,
    stage: BuildProgressionStage,
) -> tuple[BuildBreakerCertainty, RuleSeverity, str]:
    if stage == BuildProgressionStage.PRE_SWAP:
        return (
            BuildBreakerCertainty.VERIFIED_SAFE,
            RuleSeverity.INFO,
            "Pre-swap stage: Oil Grenade ignite mechanic is not active.",
        )

    # Weapon set 1 (Flameblast staff) is explicitly exempt
    if weapon_set == WeaponSetContext.WEAPON_SET_1:
        return (
            BuildBreakerCertainty.VERIFIED_SAFE,
            RuleSeverity.INFO,
            "Weapon Set 1 (Flameblast Staff) is explicitly exempt: Flameblast is a fire spell and does not affect Set 2 Oil Grenade.",
        )

    # Conditional fire modifiers have unverified uptime and attack applicability
    if mod.scope == ModifierScope.CONDITIONAL and "fire" in mod.raw_text.lower():
        return (
            BuildBreakerCertainty.UNKNOWN_APPLICABILITY,
            RuleSeverity.WARNING,
            f"Conditional modifier '{mod.raw_text}' has uncertain attack applicability; potential Oil Grenade ignite risk.",
        )

    # Check harmful modifier types for attacks
    if mod.modifier_type in (
        NormalizedModifierType.FLAT_FIRE_DAMAGE_ATTACK,
        NormalizedModifierType.EXTRA_FIRE_DAMAGE,
    ):
        return (
            BuildBreakerCertainty.VERIFIED_BUILD_BREAKER,
            RuleSeverity.BUILD_BREAKER,
            f"Harmful added Fire damage modifier '{mod.raw_text}' causes Oil Grenade attack hits to ignite early, prematurely consuming the oil pool and destroying the Flameblast damage window.",
        )

    if mod.modifier_type == NormalizedModifierType.FLAT_FIRE_DAMAGE_SPELL:
        return (
            BuildBreakerCertainty.VERIFIED_SAFE,
            RuleSeverity.INFO,
            "Flat Fire damage to Spells does not apply to Oil Grenade attack hits.",
        )

    if mod.modifier_type == NormalizedModifierType.INCREASED_FIRE_DAMAGE:
        return (
            BuildBreakerCertainty.VERIFIED_SAFE,
            RuleSeverity.INFO,
            "% increased Fire Damage scales existing fire damage without adding fire base damage to attacks.",
        )

    if mod.modifier_type in (
        NormalizedModifierType.FIRE_SPELL_LEVEL,
        NormalizedModifierType.ALL_SPELL_LEVEL,
    ):
        return (
            BuildBreakerCertainty.VERIFIED_SAFE,
            RuleSeverity.INFO,
            "Spell gem levels do not add fire damage to attacks.",
        )

    # Check for unparsed/conditional fire wording
    raw_lower = mod.raw_text.lower()
    if "fire" in raw_lower:
        # Check if it mentions damage or added/extra
        if any(w in raw_lower for w in ("damage", "extra", "gain", "added", "adds")):
            return (
                BuildBreakerCertainty.UNKNOWN_APPLICABILITY,
                RuleSeverity.WARNING,
                f"Modifier '{mod.raw_text}' contains Fire damage wording with unverified applicability to attacks; potential Oil Grenade ignite risk.",
            )

    return (
        BuildBreakerCertainty.VERIFIED_SAFE,
        RuleSeverity.INFO,
        "Modifier verified safe for Fubgun build.",
    )
