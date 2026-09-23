"""Non-scalar verdict precedence rules for equipment evaluation."""

from __future__ import annotations

from enum import Enum
from companion.equipment.requirements import RequirementCascadeResult
from companion.equipment.rules import BuildBreakerCertainty, BuildBreakerEvaluation


class Verdict(str, Enum):
    EQUIP_NOW = "EQUIP_NOW"
    CONDITIONAL_UPGRADE = "CONDITIONAL_UPGRADE"
    SIDEGRADE = "SIDEGRADE"
    STASH_FOR_LATER = "STASH_FOR_LATER"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    REJECT = "REJECT"


def evaluate_verdict_precedence(
    score_delta: float,
    safety_eval: BuildBreakerEvaluation,
    cascade_result: RequirementCascadeResult,
    unmitigated_resistance_deficit: bool = False,
) -> tuple[Verdict, str, list[str]]:
    flags: list[str] = []

    # 1. Build Breaker (Top Precedence)
    if safety_eval.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER:
        flags.append("BUILD_BREAKER")
        return (
            Verdict.REJECT,
            f"Build Breaker triggered: {safety_eval.reason}",
            flags,
        )

    # 2. Requirement Cascade Failure
    if not cascade_result.is_satisfied:
        flags.append("REQUIREMENT_DEFICIENCY")
        if cascade_result.candidate_deficiencies:
            flags.append("CANNOT_EQUIP_CANDIDATE")
            return (
                Verdict.REJECT,
                f"Candidate cannot be equipped: {cascade_result.summary}",
                flags,
            )
        return (
            Verdict.CONDITIONAL_UPGRADE,
            f"Equipping candidate breaks existing gear/gem requirements: {cascade_result.summary}",
            flags,
        )

    # 3. Resistance / Target Deficit
    if unmitigated_resistance_deficit:
        flags.append("UNMITIGATED_DEFICIT")
        return (
            Verdict.CONDITIONAL_UPGRADE,
            "Candidate causes unmitigated resistance or defensive target deficit.",
            flags,
        )

    # 4. High-Risk Unknown Gate
    if safety_eval.certainty == BuildBreakerCertainty.UNKNOWN_APPLICABILITY:
        flags.append("HIGH_RISK")
        return (
            Verdict.CONDITIONAL_UPGRADE,
            f"Candidate contains unknown modifiers with unverified build impact: {safety_eval.reason}",
            flags,
        )

    # 5. Direct Score Evaluation
    if score_delta >= 15.0:
        return (
            Verdict.EQUIP_NOW,
            f"Clear positive upgrade across evaluated stats (+{score_delta:.1f} net score).",
            flags,
        )

    if -10.0 <= score_delta < 15.0:
        if score_delta >= 0.0:
            flags.append("SIDEGRADE")
            return (
                Verdict.SIDEGRADE,
                f"Minor upgrade or sidegrade (+{score_delta:.1f} net score).",
                flags,
            )
        flags.append("STASH_FOR_LATER")
        return (
            Verdict.STASH_FOR_LATER,
            f"Slight loss on current setup ({score_delta:.1f} net score); keep for resistance/stat shifting.",
            flags,
        )

    flags.append("INFERIOR_STATS")
    return (
        Verdict.REJECT,
        f"Inferior stats compared to equipped loadout ({score_delta:.1f} net score).",
        flags,
    )
