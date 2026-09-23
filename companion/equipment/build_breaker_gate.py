"""High-Risk Unknown Gate blocking confident upgrades when safety applicability is uncertain."""

from __future__ import annotations

from companion.equipment.rules import BuildBreakerCertainty, BuildBreakerEvaluation


def apply_build_breaker_gate(
    prospective_verdict: str,
    safety_eval: BuildBreakerEvaluation,
) -> tuple[str, list[str]]:
    flags: list[str] = []

    if safety_eval.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER:
        flags.append("BUILD_BREAKER")
        return "REJECT", flags

    if safety_eval.certainty == BuildBreakerCertainty.UNKNOWN_APPLICABILITY:
        flags.append("HIGH_RISK")
        if prospective_verdict in ("EQUIP_NOW", "UPGRADE"):
            return "CONDITIONAL_UPGRADE", flags
        return prospective_verdict, flags

    return prospective_verdict, flags
