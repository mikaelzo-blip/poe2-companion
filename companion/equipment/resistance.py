"""Dynamic resistance intelligence, overcap tracking, and marginal-value evaluation."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from companion.equipment.baseline import CharacterStatBaseline


class ResistanceType(str, Enum):
    FIRE = "fire"
    COLD = "cold"
    LIGHTNING = "lightning"
    CHAOS = "chaos"


class ResistanceTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_effective: int = 75
    target_overcap_buffer: int = 20
    max_res: int = 75


class ResistanceProjection(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    res_type: ResistanceType
    current_raw: int | None = None
    current_effective: int | None = None
    current_overcap_buffer: int | None = None
    delta: float = 0.0
    projected_raw: int | None = None
    projected_effective: int | None = None
    projected_overcap_buffer: int | None = None
    deficit_before: int | None = None
    deficit_after: int | None = None
    marginal_value_score: float = 0.0


def evaluate_resistance_delta(
    baseline: CharacterStatBaseline | None,
    res_type: ResistanceType,
    delta: float,
    target: ResistanceTarget | None = None,
) -> ResistanceProjection:
    if target is None:
        if res_type == ResistanceType.CHAOS:
            target = ResistanceTarget(target_effective=0, target_overcap_buffer=0, max_res=75)
        else:
            target = ResistanceTarget(target_effective=75, target_overcap_buffer=20, max_res=75)

    if baseline is None:
        return ResistanceProjection(
            res_type=res_type,
            delta=delta,
            marginal_value_score=delta * 1.0,
        )

    # Resolve facts for this res type
    if res_type == ResistanceType.FIRE:
        raw_fact = baseline.raw_fire_res
        eff_fact = baseline.effective_fire_res
        max_fact = baseline.max_fire_res
        over_fact = baseline.fire_overcap_buffer
    elif res_type == ResistanceType.COLD:
        raw_fact = baseline.raw_cold_res
        eff_fact = baseline.effective_cold_res
        max_fact = baseline.max_cold_res
        over_fact = baseline.cold_overcap_buffer
    elif res_type == ResistanceType.LIGHTNING:
        raw_fact = baseline.raw_lightning_res
        eff_fact = baseline.effective_lightning_res
        max_fact = baseline.max_lightning_res
        over_fact = baseline.lightning_overcap_buffer
    else:
        raw_fact = baseline.raw_chaos_res
        eff_fact = baseline.effective_chaos_res
        max_fact = baseline.max_chaos_res
        over_fact = baseline.chaos_overcap_buffer

    # Raw res known
    if raw_fact.is_known and raw_fact.value is not None:
        raw_val = raw_fact.value
        max_cap = (
            max_fact.value
            if (max_fact.is_known and max_fact.value is not None)
            else target.max_res
        )
        eff_val = min(raw_val, max_cap)
        overcap = max(0, raw_val - max_cap)
        def_before = max(0, target.target_effective - eff_val)

        proj_raw = int(raw_val + delta)
        proj_eff = min(proj_raw, max_cap)
        proj_over = max(0, proj_raw - max_cap)
        def_after = max(0, target.target_effective - proj_eff)

        # Marginal value scoring
        score: float = 0.0
        if delta > 0:
            if def_before > 0:
                cured = def_before - def_after
                surplus = delta - cured
                score = cured * 4.0 + min(surplus, target.target_overcap_buffer) * 0.8 + max(0, surplus - target.target_overcap_buffer) * 0.05
            else:
                room = max(0, target.target_overcap_buffer - overcap)
                in_buffer = min(delta, room)
                excess = max(0, delta - in_buffer)
                score = in_buffer * 0.8 + excess * 0.05
        elif delta < 0:
            drop = abs(delta)
            if overcap >= drop + target.target_overcap_buffer:
                # Losing excess overcap well above buffer: zero penalty
                score = 0.0
            elif overcap >= drop:
                # Still capped at max_res, but dips into target buffer
                lost_buffer = drop - max(0, overcap - target.target_overcap_buffer)
                score = -0.05 * lost_buffer
            else:
                eff_loss = eff_val - proj_eff
                score = -(eff_loss * 12.0 + (drop - eff_loss) * 0.1)
        else:
            score = 0.0

        return ResistanceProjection(
            res_type=res_type,
            current_raw=raw_val,
            current_effective=eff_val,
            current_overcap_buffer=overcap,
            delta=delta,
            projected_raw=proj_raw,
            projected_effective=proj_eff,
            projected_overcap_buffer=proj_over,
            deficit_before=def_before,
            deficit_after=def_after,
            marginal_value_score=score,
        )

    # If raw is UNKNOWN, cannot compute projected absolute or overcap safely
    return ResistanceProjection(
        res_type=res_type,
        delta=delta,
        marginal_value_score=delta * 1.0,
    )
