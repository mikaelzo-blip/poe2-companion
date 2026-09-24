"""Non-scalar verdict precedence rules for equipment evaluation."""

from __future__ import annotations

from enum import Enum
from companion.equipment.contextual_value import LoadoutContextualAnalysis
from companion.equipment.data_sufficiency import (
    DataSufficiencyResult,
    RecommendationDataSufficiency,
)
from companion.equipment.requirements import RequirementCascadeResult
from companion.equipment.rules import BuildBreakerCertainty, BuildBreakerEvaluation


class Verdict(str, Enum):
    EQUIP_NOW = "EQUIP_NOW"
    CONDITIONAL_UPGRADE = "CONDITIONAL_UPGRADE"
    KEEP_FOR_LATER = "KEEP_FOR_LATER"
    REJECT = "REJECT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class MultidimensionalComparison(str, Enum):
    DOMINANT_IMPROVEMENT = "DOMINANT_IMPROVEMENT"
    MIXED_TRADEOFF = "MIXED_TRADEOFF"
    NO_MEANINGFUL_CURRENT_GAIN = "NO_MEANINGFUL_CURRENT_GAIN"
    CLEAR_DOWNGRADE = "CLEAR_DOWNGRADE"


def check_defense_regression(
    armour_delta: int | float = 0,
    evasion_delta: int | float = 0,
    es_delta: int | float = 0,
) -> bool:
    """Checks if candidate incurs a negative delta on local defenses."""
    return armour_delta < 0 or evasion_delta < 0 or es_delta < 0


def evaluate_contextual_verdict(
    safety_eval: BuildBreakerEvaluation,
    cascade_result: RequirementCascadeResult,
    contextual_analysis: LoadoutContextualAnalysis | None = None,
    data_sufficiency: DataSufficiencyResult | None = None,
    comparison: MultidimensionalComparison | None = None,
    has_defense_regression: bool = False,
    defense_tradeoff_reason: str | None = None,
) -> tuple[Verdict, str, list[str]]:
    """Evaluates equipment verdict using strict non-scalar precedence hierarchy.

    Strict Precedence Order:
    1. VERIFIED_BUILD_BREAKER -> REJECT (BUILD_BREAKER)
    2. Candidate unrecoverable requirement failure -> REJECT (CANNOT_EQUIP_CANDIDATE)
    3. Recoverable requirement failure (loadout cascading) -> CONDITIONAL_UPGRADE (REQUIREMENT_DEFICIENCY)
    4. UNKNOWN_APPLICABILITY build breaker -> CONDITIONAL_UPGRADE (HIGH_RISK)
    5. Insufficient data for confident equip -> INSUFFICIENT_DATA (INSUFFICIENT_DATA)
    6. Candidate creates or worsens critical defensive deficiency -> CONDITIONAL_UPGRADE (or REJECT)
    7. Known critical deficiency remains completely UNCHANGED (Case D) -> CONDITIONAL_UPGRADE (UNCHANGED_CRITICAL_DEFICIT)
    8. Candidate resolves/improves critical deficiency with no critical regression -> EQUIP_NOW (RESOLVES_DEFICIT / IMPROVES_DEFICIT)
    9. Healthy character comparison:
       - DOMINANT_IMPROVEMENT -> EQUIP_NOW
       - MIXED_TRADEOFF -> CONDITIONAL_UPGRADE or KEEP_FOR_LATER
       - NO_MEANINGFUL_CURRENT_GAIN -> KEEP_FOR_LATER
       - CLEAR_DOWNGRADE -> REJECT
    """
    flags: list[str] = []

    # 1. Build Breaker (Top Precedence)
    if safety_eval.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER:
        flags.append("BUILD_BREAKER")
        return (
            Verdict.REJECT,
            f"Build Breaker triggered: {safety_eval.reason}",
            flags,
        )

    # 2. Candidate unrecoverable requirement failure
    if not cascade_result.is_satisfied:
        flags.append("REQUIREMENT_DEFICIENCY")
        if cascade_result.candidate_deficiencies:
            flags.append("CANNOT_EQUIP_CANDIDATE")
            return (
                Verdict.REJECT,
                f"Candidate cannot be equipped: {cascade_result.summary}",
                flags,
            )
        # 3. Recoverable requirement failure (equipped gear/gems)
        return (
            Verdict.CONDITIONAL_UPGRADE,
            f"Equipping candidate breaks existing gear/gem requirements: {cascade_result.summary}",
            flags,
        )

    # 4. UNKNOWN_APPLICABILITY build breaker
    if safety_eval.certainty == BuildBreakerCertainty.UNKNOWN_APPLICABILITY:
        flags.append("HIGH_RISK")
        return (
            Verdict.CONDITIONAL_UPGRADE,
            f"Candidate contains unknown modifiers with unverified build impact: {safety_eval.reason}",
            flags,
        )

    # 5. Insufficient data for confident equip
    if data_sufficiency is not None:
        if data_sufficiency.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP:
            flags.append("INSUFFICIENT_DATA")
            reason_msg = "; ".join(data_sufficiency.reasons) if data_sufficiency.reasons else "Insufficient data for confident equip."
            return (
                Verdict.INSUFFICIENT_DATA,
                reason_msg,
                flags,
            )

    # Contextual deficiency checks (Steps 6, 7, 8)
    if contextual_analysis is not None:
        # 6. Candidate creates or worsens critical defensive deficiency
        if contextual_analysis.has_worsened_deficiency:
            flags.append("WORSENS_DEFICIENCY")
            flags.append("UNMITIGATED_DEFICIT")
            return (
                Verdict.CONDITIONAL_UPGRADE,
                "Candidate worsens an existing defensive or requirement deficiency.",
                flags,
            )
        if contextual_analysis.has_created_deficiency:
            flags.append("CREATES_DEFICIENCY")
            flags.append("UNMITIGATED_DEFICIT")
            return (
                Verdict.CONDITIONAL_UPGRADE,
                "Candidate creates a new defensive or requirement deficiency.",
                flags,
            )

        # 7. Known critical deficiency remains completely UNCHANGED (Case D)
        if contextual_analysis.has_unchanged_critical_deficiency:
            flags.append("UNCHANGED_CRITICAL_DEFICIT")
            details = "; ".join(contextual_analysis.critical_deficiency_details) if contextual_analysis.critical_deficiency_details else "Unchanged critical deficit."
            return (
                Verdict.CONDITIONAL_UPGRADE,
                f"Candidate leaves critical character deficiency unaddressed: {details}",
                flags,
            )

        # 8. Candidate resolves/improves critical deficiency with no critical regression
        if not has_defense_regression:
            if contextual_analysis.has_resolved_deficiency:
                flags.append("RESOLVES_DEFICIT")
                return (
                    Verdict.EQUIP_NOW,
                    "Candidate resolves a critical defensive or requirement deficiency without critical regressions.",
                    flags,
                )
            if contextual_analysis.has_improved_deficiency:
                flags.append("IMPROVES_DEFICIT")
                return (
                    Verdict.EQUIP_NOW,
                    "Candidate improves a critical defensive or requirement deficiency without critical regressions.",
                    flags,
                )

    # 9. Healthy character comparison (or default when no deficiencies)
    effective_comparison = comparison or (
        MultidimensionalComparison.MIXED_TRADEOFF if has_defense_regression else MultidimensionalComparison.DOMINANT_IMPROVEMENT
    )
    if has_defense_regression and effective_comparison == MultidimensionalComparison.DOMINANT_IMPROVEMENT:
        effective_comparison = MultidimensionalComparison.MIXED_TRADEOFF

    if effective_comparison == MultidimensionalComparison.DOMINANT_IMPROVEMENT:
        return (
            Verdict.EQUIP_NOW,
            "Clear positive upgrade across evaluated stats.",
            flags,
        )
    if effective_comparison == MultidimensionalComparison.MIXED_TRADEOFF:
        flags.append("MIXED_TRADEOFF")
        tradeoff_reason = defense_tradeoff_reason or (
            "Candidate incurs regression on local defenses; represents a mixed defense tradeoff."
            if has_defense_regression
            else "Mixed tradeoff against equipped loadout; provides situational value."
        )
        return (
            Verdict.CONDITIONAL_UPGRADE,
            tradeoff_reason,
            flags,
        )
    if effective_comparison == MultidimensionalComparison.NO_MEANINGFUL_CURRENT_GAIN:
        flags.append("NO_CURRENT_GAIN")
        return (
            Verdict.KEEP_FOR_LATER,
            "No meaningful current gain over equipped loadout; retain for future gear/stat shifting.",
            flags,
        )
    if effective_comparison == MultidimensionalComparison.CLEAR_DOWNGRADE:
        flags.append("CLEAR_DOWNGRADE")
        return (
            Verdict.REJECT,
            "Inferior stats across evaluated dimensions compared to equipped loadout.",
            flags,
        )

    return (
        Verdict.KEEP_FOR_LATER,
        "No clear upgrade path identified.",
        flags,
    )


def evaluate_verdict_precedence(
    safety_eval: BuildBreakerEvaluation,
    cascade_result: RequirementCascadeResult,
    unmitigated_resistance_deficit: bool = False,
    score_delta: float | None = None,
    contextual_analysis: LoadoutContextualAnalysis | None = None,
    data_sufficiency: DataSufficiencyResult | None = None,
    comparison: MultidimensionalComparison | None = None,
    has_defense_regression: bool = False,
    defense_tradeoff_reason: str | None = None,
) -> tuple[Verdict, str, list[str]]:
    """Backward-compatible entry point for verdict precedence evaluation.

    Score delta is accepted but does not determine verdict. Non-scalar contextual
    and requirement evaluations govern all outcomes.
    """
    # 1. Build Breaker (Top Precedence)
    if safety_eval.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER:
        return (
            Verdict.REJECT,
            f"Build Breaker triggered: {safety_eval.reason}",
            ["BUILD_BREAKER"],
        )

    # 2. Requirement Cascade Failure
    if not cascade_result.is_satisfied:
        flags = ["REQUIREMENT_DEFICIENCY"]
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

    # 3. Unmitigated Resistance / Target Deficit (legacy / direct flag)
    if unmitigated_resistance_deficit:
        return (
            Verdict.CONDITIONAL_UPGRADE,
            "Candidate causes unmitigated resistance or defensive target deficit.",
            ["UNMITIGATED_DEFICIT"],
        )

    # 4. High-Risk Unknown Gate
    if safety_eval.certainty == BuildBreakerCertainty.UNKNOWN_APPLICABILITY:
        return (
            Verdict.CONDITIONAL_UPGRADE,
            f"Candidate contains unknown modifiers with unverified build impact: {safety_eval.reason}",
            ["HIGH_RISK"],
        )

    # If contextual analysis or data sufficiency provided, delegate to contextual evaluator
    if (
        contextual_analysis is not None
        or data_sufficiency is not None
        or comparison is not None
        or has_defense_regression
    ):
        return evaluate_contextual_verdict(
            safety_eval=safety_eval,
            cascade_result=cascade_result,
            contextual_analysis=contextual_analysis,
            data_sufficiency=data_sufficiency,
            comparison=comparison,
            has_defense_regression=has_defense_regression,
            defense_tradeoff_reason=defense_tradeoff_reason,
        )

    # If comparison not provided and no unmitigated deficit or build breaker, default to EQUIP_NOW
    return (
        Verdict.EQUIP_NOW,
        "Candidate passes all safety and requirement checks.",
        [],
    )
