"""Recommendation domain models and factual comparison reporting."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from companion.equipment.partial_projection import PartialLoadoutProjection, StatProjection
from companion.equipment.precedence import Verdict
from companion.equipment.requirements import RequirementCascadeResult
from companion.equipment.rules import BuildBreakerCertainty, BuildBreakerEvaluation
from companion.equipment.schema import ItemCandidate, SlotType, WeaponSetContext


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
    score_delta: float = 0.0
    actionable_guidance: list[str] = Field(default_factory=list)

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
        f"VERDICT: {rec.verdict.value}",
        f"Reason:  {rec.verdict_reason}",
    ]

    if rec.flags:
        lines.append(f"Flags:   {', '.join(rec.flags)}")

    lines.append("")
    if rec.displaced_items:
        disp_names = ", ".join(f"{it.name} ({it.base_type})" for it in rec.displaced_items)
        lines.append(f"Displaced Item(s): {disp_names}")
    else:
        lines.append("Displaced Item(s): None (Empty slot)")

    lines.append("")
    lines.append("--- STAT COMPARISON (KNOWN DELTAS vs PROJECTED ABSOLUTES) ---")
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
    if rec.safety_eval.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER:
        lines.append("--- BUILD-BREAKER SAFETY: VERIFIED_BUILD_BREAKER [BUILD BREAKER DETECTED] ---")
    elif rec.safety_eval.certainty == BuildBreakerCertainty.UNKNOWN_APPLICABILITY:
        lines.append("--- BUILD-BREAKER SAFETY: UNKNOWN_APPLICABILITY [HIGH RISK UNKNOWN WARNING] ---")
    else:
        lines.append(f"--- BUILD-BREAKER SAFETY: {rec.safety_eval.certainty.value} ---")
    lines.append(f"  {rec.safety_eval.reason}")

    lines.append("")
    lines.append("--- REQUIREMENT CASCADES ---")
    lines.append(f"  {rec.cascade_result.summary}")
    for d in rec.cascade_result.loadout_cascading_deficiencies:
        lines.append(f"  * Warning: Replaces Dex/Str needed by {d.target_name} (Shortfall: {d.shortfall})")
    for d in rec.cascade_result.gem_cascading_deficiencies:
        lines.append(f"  * Warning: Replaces attribute needed by socketed gem {d.target_name} (Shortfall: {d.shortfall})")

    if rec.actionable_guidance:
        lines.append("")
        lines.append("--- ACTIONABLE GUIDANCE ---")
        for g in rec.actionable_guidance:
            lines.append(f"  * {g}")

    lines.append("============================================================")
    return "\n".join(lines)
