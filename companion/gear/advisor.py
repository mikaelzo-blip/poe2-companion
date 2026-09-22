"""Investment advice and candidate upgrade evaluation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from companion.gear.evaluator import _extract_mod_values
from companion.gear.schema import EquippedItem, ItemSlot


class InvestmentAdvice(BaseModel):
    """Actionable investment and durability advice for an equipped item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: ItemSlot
    needs_replacement: bool
    recommendation: str
    durability_score: float = 0.0


class UpgradeComparison(BaseModel):
    """Comparison between an equipped item and an unequipped candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: str  # "UPGRADE", "RETAIN", "SIDEGRADE"
    score_delta: float
    breakdown: dict[str, float] = Field(default_factory=dict)


def _compute_item_defensive_score(item: EquippedItem) -> float:
    """Compute heuristic defensive value score based on life, resists, and level."""
    mods = _extract_mod_values(item)
    score = float(item.level_req * 0.5)
    score += mods.get("life", 0.0) * 1.0
    score += mods.get("fire_res", 0.0) * 1.2
    score += mods.get("cold_res", 0.0) * 1.2
    score += mods.get("lightning_res", 0.0) * 1.2
    score += mods.get("chaos_res", 0.0) * 1.5
    return score


def generate_investment_advice(
    item: EquippedItem,
    upcoming_milestone_level: int = 52,
) -> InvestmentAdvice:
    """Advise whether an equipped item possesses adequate durability for future progression."""
    score = _compute_item_defensive_score(item)

    # If the item's level requirement is far behind the upcoming milestone
    level_gap = upcoming_milestone_level - item.level_req
    needs_replacement = level_gap > 20 or score < 40.0

    if needs_replacement:
        rec = (
            f"Low item durability for {item.slot.value} ({item.base_type}, req lvl {item.level_req}). "
            f"Recommend replacing prior to reaching level {upcoming_milestone_level}."
        )
    else:
        rec = f"Durability sufficient for upcoming progression milestone {upcoming_milestone_level}."

    return InvestmentAdvice(
        slot=item.slot,
        needs_replacement=needs_replacement,
        recommendation=rec,
        durability_score=score,
    )


def compare_candidate_upgrade(
    equipped: EquippedItem,
    candidate: EquippedItem,
) -> UpgradeComparison:
    """Compare candidate upgrade item against currently equipped slot item."""
    eq_score = _compute_item_defensive_score(equipped)
    cand_score = _compute_item_defensive_score(candidate)
    delta = cand_score - eq_score

    if delta >= 10.0:
        action = "UPGRADE"
    elif delta <= -10.0:
        action = "RETAIN"
    else:
        action = "SIDEGRADE"

    eq_mods = _extract_mod_values(equipped)
    cand_mods = _extract_mod_values(candidate)

    all_keys = set(eq_mods.keys()) | set(cand_mods.keys())
    breakdown = {k: cand_mods.get(k, 0.0) - eq_mods.get(k, 0.0) for k in all_keys}

    return UpgradeComparison(
        action=action,
        score_delta=delta,
        breakdown=breakdown,
    )
