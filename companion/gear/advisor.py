"""Target-driven factual gear comparison and investment advice.

Replaces unsourced weighted scoring formulas and magic thresholds with factual,
verified target requirement comparisons adhering to the M8 provenance policy.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from companion.gear.evaluator import _extract_mod_values
from companion.gear.schema import ComparisonVerdict, EquippedItem, ItemSlot
from companion.state.provenance import VerificationState


class InvestmentAdvice(BaseModel):
    """Actionable investment and requirement-match advice for an equipped item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: ItemSlot
    needs_replacement: bool
    recommendation: str
    satisfied_requirements: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)


class UpgradeComparison(BaseModel):
    """Comparison between an equipped item and an unequipped candidate against target requirements."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: ComparisonVerdict
    candidate_satisfied: list[str] = Field(default_factory=list)
    candidate_missing: list[str] = Field(default_factory=list)
    equipped_satisfied: list[str] = Field(default_factory=list)
    equipped_missing: list[str] = Field(default_factory=list)
    trade_offs: dict[str, str] = Field(default_factory=dict)
    breakdown: dict[str, float] = Field(default_factory=dict)


def _evaluate_requirements(
    item: EquippedItem,
    target_requirements: dict[str, float | int | str],
) -> tuple[list[str], list[str]]:
    """Determine which target requirements are satisfied vs missing for an item."""
    mod_values = _extract_mod_values(item)
    satisfied: list[str] = []
    missing: list[str] = []

    for req_key, req_val in target_requirements.items():
        if isinstance(req_val, (int, float)):
            if req_key == "level_req":
                actual_val = float(item.level_req)
            elif req_key == "item_level":
                actual_val = float(item.item_level)
            else:
                actual_val = mod_values.get(req_key, 0.0)

            if actual_val >= req_val:
                satisfied.append(req_key)
            else:
                missing.append(req_key)
        elif isinstance(req_val, str):
            if req_val.lower() in item.base_type.lower():
                satisfied.append(req_key)
            else:
                missing.append(req_key)

    return satisfied, missing


def generate_investment_advice(
    item: EquippedItem,
    target_requirements: dict[str, float | int | str] | None = None,
    upcoming_milestone_level: int = 52,
) -> InvestmentAdvice:
    """Advise whether an equipped item meets verified requirements for upcoming progression."""
    if not target_requirements:
        return InvestmentAdvice(
            slot=item.slot,
            needs_replacement=False,
            recommendation=f"No verified target requirements for {item.slot.value}. Item attributes preserved.",
            satisfied_requirements=[],
            missing_requirements=[],
        )

    satisfied, missing = _evaluate_requirements(item, target_requirements)
    needs_replacement = len(missing) > 0

    if needs_replacement:
        rec = (
            f"Item in {item.slot.value} ({item.base_type}) missing verified requirements: "
            f"{', '.join(missing)} for milestone {upcoming_milestone_level}."
        )
    else:
        rec = (
            f"Item in {item.slot.value} satisfies all {len(satisfied)} verified requirements "
            f"for milestone {upcoming_milestone_level}."
        )

    return InvestmentAdvice(
        slot=item.slot,
        needs_replacement=needs_replacement,
        recommendation=rec,
        satisfied_requirements=satisfied,
        missing_requirements=missing,
    )


def compare_candidate_upgrade(
    equipped: EquippedItem,
    candidate: EquippedItem,
    target_requirements: dict[str, float | int | str] | None = None,
) -> UpgradeComparison:
    """Compare candidate upgrade item against currently equipped slot item based on target requirements."""
    eq_mods = _extract_mod_values(equipped)
    cand_mods = _extract_mod_values(candidate)
    all_keys = set(eq_mods.keys()) | set(cand_mods.keys())
    breakdown = {k: cand_mods.get(k, 0.0) - eq_mods.get(k, 0.0) for k in all_keys}

    if not target_requirements:
        return UpgradeComparison(
            verdict=ComparisonVerdict.UNKNOWN,
            candidate_satisfied=[],
            candidate_missing=[],
            equipped_satisfied=[],
            equipped_missing=[],
            trade_offs={},
            breakdown=breakdown,
        )

    if (
        equipped.verification == VerificationState.UNKNOWN
        or candidate.verification == VerificationState.UNKNOWN
    ):
        return UpgradeComparison(
            verdict=ComparisonVerdict.UNKNOWN,
            candidate_satisfied=[],
            candidate_missing=[],
            equipped_satisfied=[],
            equipped_missing=[],
            trade_offs={},
            breakdown=breakdown,
        )

    eq_sat, eq_miss = _evaluate_requirements(equipped, target_requirements)
    cand_sat, cand_miss = _evaluate_requirements(candidate, target_requirements)

    set_eq = set(eq_sat)
    set_cand = set(cand_sat)

    trade_offs: dict[str, str] = {}
    if set_eq.issubset(set_cand) and len(set_cand) > len(set_eq):
        verdict = ComparisonVerdict.SATISFIES_MORE_VERIFIED_REQUIREMENTS
    elif set_cand.issubset(set_eq) and len(set_cand) < len(set_eq):
        verdict = ComparisonVerdict.SATISFIES_FEWER_VERIFIED_REQUIREMENTS
    elif set_cand == set_eq:
        verdict = ComparisonVerdict.EQUIVALENT_FOR_KNOWN_REQUIREMENTS
    else:
        verdict = ComparisonVerdict.INCOMPARABLE
        gained = sorted(set_cand - set_eq)
        lost = sorted(set_eq - set_cand)
        if gained:
            trade_offs["gained"] = ", ".join(gained)
        if lost:
            trade_offs["lost"] = ", ".join(lost)

    return UpgradeComparison(
        verdict=verdict,
        candidate_satisfied=cand_sat,
        candidate_missing=cand_miss,
        equipped_satisfied=eq_sat,
        equipped_missing=eq_miss,
        trade_offs=trade_offs,
        breakdown=breakdown,
    )
