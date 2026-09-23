"""Build-breaker evaluation engine assessing modifier safety against active build mechanics."""

from __future__ import annotations

from companion.equipment.fubgun_rules import evaluate_fubgun_modifier
from companion.equipment.rules import (
    BuildBreakerCertainty,
    BuildBreakerEvaluation,
    BuildProgressionStage,
    RuleSeverity,
)
from companion.equipment.schema import (
    ItemCandidate,
    NormalizedModifier,
    SlotType,
    WeaponSetContext,
)


def evaluate_candidate_build_safety(
    candidate: ItemCandidate,
    slot: SlotType,
    weapon_set: WeaponSetContext | None = None,
    stage: BuildProgressionStage = BuildProgressionStage.EARLY_ENDGAME,
) -> BuildBreakerEvaluation:
    wset = weapon_set or candidate.weapon_set
    # If candidate is a staff and no weapon set specified, default to Set 1 (Flameblast staff)
    if not wset and "staff" in (candidate.base_type or "").lower():
        wset = WeaponSetContext.WEAPON_SET_1

    unknown_eval: tuple[BuildBreakerCertainty, RuleSeverity, str, NormalizedModifier] | None = None

    for mod in candidate.modifiers:
        certainty, severity, reason = evaluate_fubgun_modifier(
            mod=mod,
            slot=slot,
            weapon_set=wset,
            stage=stage,
        )

        if certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER:
            return BuildBreakerEvaluation(
                certainty=BuildBreakerCertainty.VERIFIED_BUILD_BREAKER,
                severity=RuleSeverity.BUILD_BREAKER,
                rule_name="FubgunOilGrenadeFireRule",
                reason=reason,
                violating_modifiers=[mod],
            )

        if certainty == BuildBreakerCertainty.UNKNOWN_APPLICABILITY and unknown_eval is None:
            unknown_eval = (certainty, severity, reason, mod)

    if unknown_eval is not None:
        cert, sev, rsn, mod = unknown_eval
        return BuildBreakerEvaluation(
            certainty=cert,
            severity=sev,
            rule_name="FubgunOilGrenadeFireRule",
            reason=rsn,
            violating_modifiers=[mod],
        )

    return BuildBreakerEvaluation(
        certainty=BuildBreakerCertainty.VERIFIED_SAFE,
        severity=RuleSeverity.INFO,
        rule_name="FubgunOilGrenadeFireRule",
        reason="All candidate modifiers verified safe against active build mechanics.",
        violating_modifiers=[],
    )
