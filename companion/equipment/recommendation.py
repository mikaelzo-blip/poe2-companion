"""Recommendation domain models and factual comparison reporting."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from companion.equipment.contextual_value import (
    DeficiencyImpact,
    LoadoutContextualAnalysis,
)
from companion.equipment.data_sufficiency import DataSufficiencyResult
from companion.equipment.mechanics import lookup_special_mechanic
from companion.equipment.partial_projection import PartialLoadoutProjection, StatProjection
from companion.equipment.precedence import Verdict
from companion.equipment.requirements import RequirementCascadeResult
from companion.equipment.rules import (
    BuildBreakerCertainty,
    BuildBreakerEvaluation,
    BuildProgressionStage,
)
from companion.equipment.schema import (
    ItemCandidate,
    NormalizedModifier,
    SlotType,
    WeaponSetContext,
)


class EquipmentRecommendation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    character_id: str
    slot: SlotType
    target_weapon_set: WeaponSetContext | None = None
    candidate: ItemCandidate
    displaced_items: list[ItemCandidate] = Field(default_factory=list)
    projection: PartialLoadoutProjection
    safety_eval: BuildBreakerEvaluation
    cascade_result: RequirementCascadeResult
    verdict: Verdict
    verdict_reason: str
    flags: list[str] = Field(default_factory=list)
    sufficiency: DataSufficiencyResult | None = None
    contextual_analysis: LoadoutContextualAnalysis | None = None
    actionable_guidance: list[str] = Field(default_factory=list)
    stage: BuildProgressionStage | None = None
    guide_priority: str | None = None

    @property
    def displaced_build_mechanics(self) -> list[NormalizedModifier]:
        return self.projection.displaced_build_mechanics

    @property
    def candidate_build_mechanics(self) -> list[NormalizedModifier]:
        return self.projection.candidate_build_mechanics

    @property
    def removed_build_mechanics(self) -> list[NormalizedModifier]:
        return self.projection.removed_build_mechanics

    @property
    def added_build_mechanics(self) -> list[NormalizedModifier]:
        return self.projection.added_build_mechanics

    @property
    def preserved_build_mechanics(self) -> list[NormalizedModifier]:
        return self.projection.preserved_build_mechanics

    @property
    def formatted_report(self) -> str:
        return format_recommendation_report(self)


def format_stat_delta(stat_name: str, proj: StatProjection, suffix: str = "") -> str:
    sign = "+" if proj.delta > 0 else ""
    delta_str = f"{sign}{proj.delta:g}{suffix}"
    abs_str = f"{proj.projected_absolute}{suffix}" if proj.is_absolute_known else "UNKNOWN"
    return f"  {stat_name:<16}: Delta {delta_str:<10} | Projected: {abs_str}"


def format_recommendation_report(rec: EquipmentRecommendation) -> str:
    lines: list[str] = [
        "============================================================",
        f"EQUIPMENT INTELLIGENCE EVALUATION: {rec.candidate.name.upper()}",
        f"Item: {rec.candidate.name} ({rec.candidate.base_type})",
        f"Slot: {rec.slot.value.upper()}" + (f" ({rec.target_weapon_set.value})" if rec.target_weapon_set else ""),
        f"Base: {rec.candidate.base_type} (Rarity: {rec.candidate.rarity.capitalize()})",
        "============================================================",
        "--- VERDICT ---",
        f"  Verdict: {rec.verdict.value}",
    ]
    if rec.flags:
        lines.append(f"  Flags:   {', '.join(rec.flags)}")

    lines.append("")
    lines.append("--- WHY ---")
    lines.append(f"  {rec.verdict_reason}")

    # Helper lists for deficiency categorization
    crit_deficiencies: list[str] = []
    gear_priorities: list[str] = []
    deficiencies_resolved: list[str] = []
    deficiencies_remaining: list[str] = []
    new_deficiencies: list[str] = []

    if rec.contextual_analysis is not None:
        ca = rec.contextual_analysis
        for res_type, r_ana in ca.resistances.items():
            r_name = res_type.value.capitalize()
            if r_ana.is_hard_target:
                if r_ana.deficit_before > 0:
                    crit_deficiencies.append(
                        f"{r_name} Resistance: {r_ana.deficit_before}% deficit before (hard target {r_ana.target}%)"
                    )
                if r_ana.impact == DeficiencyImpact.RESOLVES:
                    deficiencies_resolved.append(
                        f"{r_name} Resistance: Deficit fully resolved (+{r_ana.delta:g}%, projected {r_ana.projected_effective}%)"
                    )
                elif r_ana.impact == DeficiencyImpact.IMPROVES:
                    deficiencies_resolved.append(
                        f"{r_name} Resistance: Deficit reduced from {r_ana.deficit_before}% to {r_ana.deficit_after}%"
                    )
                elif r_ana.impact == DeficiencyImpact.UNCHANGED and r_ana.deficit_before > 0:
                    deficiencies_remaining.append(
                        f"{r_name} Resistance: Deficit unchanged at {r_ana.deficit_before}% short of {r_ana.target}%"
                    )
                elif r_ana.impact == DeficiencyImpact.WORSENS:
                    new_deficiencies.append(
                        f"{r_name} Resistance: Deficit worsened by {abs(r_ana.delta):g}% (now {r_ana.deficit_after}% short)"
                    )
                elif r_ana.impact == DeficiencyImpact.CREATES_NEW_DEFICIENCY:
                    new_deficiencies.append(
                        f"{r_name} Resistance: New deficit created ({r_ana.deficit_after}% short of {r_ana.target}%)"
                    )
            else:
                # Reference-only campaign resistance
                if r_ana.gap_before > 0 and r_ana.current_effective is not None:
                    gear_priorities.append(
                        f"{r_name} Resistance: {r_ana.current_effective}% | Reference cap: {r_ana.reference_cap}% | Status: LOW / HIGH GEAR PRIORITY"
                    )
                if r_ana.impact == DeficiencyImpact.RESOLVES:
                    deficiencies_resolved.append(
                        f"{r_name} Resistance: Resolved reference cap gap (+{r_ana.delta:g}%, reached {r_ana.projected_effective}%)"
                    )
                elif r_ana.impact == DeficiencyImpact.IMPROVES:
                    deficiencies_resolved.append(
                        f"{r_name} Resistance: Improved from {r_ana.current_effective}% to {r_ana.projected_effective}% (reference cap {r_ana.reference_cap}%)"
                    )
                elif r_ana.impact == DeficiencyImpact.WORSENS:
                    new_deficiencies.append(
                        f"{r_name} Resistance: Regressed by {abs(r_ana.delta):g}% (from {r_ana.current_effective}% to {r_ana.projected_effective}%)"
                    )
                elif r_ana.impact == DeficiencyImpact.CREATES_NEW_DEFICIENCY:
                    new_deficiencies.append(
                        f"{r_name} Resistance: Capped state lost (dropped from {r_ana.current_effective}% to {r_ana.projected_effective}%, reference cap {r_ana.reference_cap}%)"
                    )

        for attr_name, a_ana in ca.attributes.items():
            aname_cap = attr_name.capitalize()
            if a_ana.deficit_before > 0:
                crit_deficiencies.append(
                    f"{aname_cap} Attribute: {a_ana.deficit_before} deficit before (required {a_ana.highest_required})"
                )
            if a_ana.impact == DeficiencyImpact.RESOLVES:
                deficiencies_resolved.append(
                    f"{aname_cap} Attribute: Requirement met (+{a_ana.delta:g}, projected {a_ana.projected_value})"
                )
            elif a_ana.impact == DeficiencyImpact.IMPROVES:
                deficiencies_resolved.append(
                    f"{aname_cap} Attribute: Deficit reduced from {a_ana.deficit_before} to {a_ana.deficit_after}"
                )
            elif a_ana.impact == DeficiencyImpact.UNCHANGED and a_ana.deficit_before > 0:
                deficiencies_remaining.append(
                    f"{aname_cap} Attribute: Deficit unchanged at {a_ana.deficit_before} short of {a_ana.highest_required}"
                )
            elif a_ana.impact == DeficiencyImpact.WORSENS:
                new_deficiencies.append(
                    f"{aname_cap} Attribute: Deficit worsened by {abs(a_ana.delta):g} (now {a_ana.deficit_after} short)"
                )
            elif a_ana.impact == DeficiencyImpact.CREATES_NEW_DEFICIENCY:
                new_deficiencies.append(
                    f"{aname_cap} Attribute: New deficit created ({a_ana.deficit_after} short of {a_ana.highest_required})"
                )

    if gear_priorities:
        lines.append("")
        lines.append("--- GEAR RESISTANCE PRIORITIES (REFERENCE ONLY) ---")
        for gp in gear_priorities:
            lines.append(f"  * {gp}")

    lines.append("")
    lines.append("--- CRITICAL DEFICIENCIES ---")
    if crit_deficiencies:
        for c in crit_deficiencies:
            lines.append(f"  * {c}")
    else:
        lines.append("  None identified.")

    lines.append("")
    lines.append("--- DEFICIENCIES RESOLVED ---")
    if deficiencies_resolved:
        for r in deficiencies_resolved:
            lines.append(f"  * {r}")
    else:
        lines.append("  None.")

    lines.append("")
    lines.append("--- DEFICIENCIES REMAINING ---")
    if deficiencies_remaining:
        for rm in deficiencies_remaining:
            lines.append(f"  * {rm}")
    else:
        lines.append("  None.")

    lines.append("")
    lines.append("--- NEW DEFICIENCIES ---")
    if new_deficiencies:
        for nd in new_deficiencies:
            lines.append(f"  * {nd}")
    else:
        lines.append("  None.")

    lines.append("")
    if rec.displaced_items:
        disp_names = ", ".join(f"{it.name} ({it.base_type})" for it in rec.displaced_items)
        lines.append(f"Displaced Item(s): {disp_names}")
    else:
        lines.append("Displaced Item(s): None (Empty slot)")

    lines.append("")
    lines.append("--- KNOWN STAT DELTAS (KNOWN DELTAS vs PROJECTED ABSOLUTES) ---")
    p = rec.projection
    lines.append(format_stat_delta("Life", p.life))
    lines.append(format_stat_delta("Fire Res", p.fire_res, "%"))
    lines.append(format_stat_delta("Cold Res", p.cold_res, "%"))
    lines.append(format_stat_delta("Lightning Res", p.lightning_res, "%"))
    lines.append(format_stat_delta("Chaos Res", p.chaos_res, "%"))
    lines.append(format_stat_delta("Strength", p.strength))
    lines.append(format_stat_delta("Dexterity", p.dexterity))
    lines.append(format_stat_delta("Intelligence", p.intelligence))
    lines.append(format_stat_delta("Movement Speed", p.movement_speed, "%"))

    # Local defenses
    if p.local_armour_delta or p.local_evasion_delta or p.local_energy_shield_delta:
        lines.append("  Local Defenses  : " + ", ".join(filter(None, [
            f"Armour {p.local_armour_delta:+d}" if p.local_armour_delta else None,
            f"Evasion {p.local_evasion_delta:+d}" if p.local_evasion_delta else None,
            f"ES {p.local_energy_shield_delta:+d}" if p.local_energy_shield_delta else None,
        ])) + " | Total Char Defenses: ISOLATED (Not Fabricated)")

    lines.append("")
    lines.append("--- REQUIREMENT EFFECT ---")
    lines.append(f"  {rec.cascade_result.summary}")
    for d in rec.cascade_result.loadout_cascading_deficiencies:
        lines.append(f"  * Warning: Replaces Dex/Str needed by {d.target_name} (Shortfall: {d.shortfall})")
    for d in rec.cascade_result.gem_cascading_deficiencies:
        lines.append(f"  * Warning: Replaces attribute needed by socketed gem {d.target_name} (Shortfall: {d.shortfall})")

    lines.append("")
    lines.append("--- BUILD MECHANICS ---")
    p = rec.projection
    has_mechanics = bool(
        p.displaced_build_mechanics
        or p.candidate_build_mechanics
        or p.removed_build_mechanics
        or p.added_build_mechanics
        or p.preserved_build_mechanics
    )
    if has_mechanics:
        lines.append("  Removed:")
        if p.removed_build_mechanics:
            for m in p.removed_build_mechanics:
                defn = lookup_special_mechanic(m)
                lines.append(f"    * {defn.canonical_name} [{defn.projection_support.value}]")
        else:
            lines.append("    * None")

        lines.append("  Added:")
        if p.added_build_mechanics:
            for m in p.added_build_mechanics:
                defn = lookup_special_mechanic(m)
                lines.append(f"    * {defn.canonical_name} [{defn.projection_support.value}]")
        else:
            lines.append("    * None")

        if p.preserved_build_mechanics:
            lines.append("  Preserved:")
            for m in p.preserved_build_mechanics:
                defn = lookup_special_mechanic(m)
                lines.append(f"    * {defn.canonical_name} [{defn.projection_support.value}]")
    else:
        lines.append("  No special build mechanics on displaced or candidate item.")

    lines.append("")
    if rec.safety_eval.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER:
        lines.append("--- BUILD-MECHANIC SAFETY: VERIFIED_BUILD_BREAKER [BUILD BREAKER DETECTED] ---")
    elif rec.safety_eval.certainty == BuildBreakerCertainty.UNKNOWN_APPLICABILITY:
        lines.append("--- BUILD-MECHANIC SAFETY: UNKNOWN_APPLICABILITY [HIGH RISK UNKNOWN WARNING] ---")
    else:
        lines.append(f"--- BUILD-MECHANIC SAFETY: {rec.safety_eval.certainty.value} ---")
    lines.append(f"  {rec.safety_eval.reason}")

    lines.append("")
    lines.append("--- UNCERTAINTIES ---")
    uncertainty_items: list[str] = []
    if rec.sufficiency is not None:
        for r in rec.sufficiency.reasons:
            if r not in uncertainty_items:
                uncertainty_items.append(r)
        for u in rec.sufficiency.unobserved_critical_facts:
            msg = f"Unobserved baseline stat: {u}"
            if msg not in uncertainty_items:
                uncertainty_items.append(msg)
    if uncertainty_items:
        for u in uncertainty_items:
            lines.append(f"  * {u}")
    else:
        lines.append("  None identified.")

    lines.append("")
    lines.append("--- TRADEOFFS ---")
    tradeoffs: list[str] = []
    if rec.actionable_guidance:
        tradeoffs.extend(rec.actionable_guidance)
    if not tradeoffs:
        tradeoffs.append("No adverse tradeoffs detected.")
    for t in tradeoffs:
        lines.append(f"  * {t}")

    lines.append("============================================================")
    return "\n".join(lines)
