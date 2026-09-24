"""Data-sufficiency analysis model for equipment intelligence recommendations."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.mechanics import MechanicSafetyAssessment, evaluate_mechanic_safety
from companion.equipment.rules import BuildBreakerCertainty, BuildBreakerEvaluation
from companion.equipment.schema import (
    ItemCandidate,
    NormalizedModifierType,
    SlotOccupancy,
    SlotType,
)


class RecommendationDataSufficiency(str, Enum):
    """Classification of data sufficiency for recommendation confidence."""

    SUFFICIENT = "SUFFICIENT"
    PARTIAL_SAFE = "PARTIAL_SAFE"
    INSUFFICIENT_FOR_CONFIDENT_EQUIP = "INSUFFICIENT_FOR_CONFIDENT_EQUIP"


class DataSufficiencyResult(BaseModel):
    """Detailed outcome of data-sufficiency analysis."""

    model_config = ConfigDict(frozen=True)

    sufficiency: RecommendationDataSufficiency
    reasons: list[str] = Field(default_factory=list)
    is_sufficient_for_equip_now: bool = False
    is_slot_known: bool = True
    is_baseline_anchored: bool = True
    is_safety_verified: bool = True
    is_mechanics_safe: bool = True
    unobserved_critical_facts: list[str] = Field(default_factory=list)


def analyze_data_sufficiency(
    baseline: CharacterStatBaseline | None,
    loadout: EquippedLoadout | None,
    candidate: ItemCandidate,
    slot: SlotType,
    safety_eval: BuildBreakerEvaluation,
    projection: Any = None,
    mechanic_assessment: MechanicSafetyAssessment | None = None,
) -> DataSufficiencyResult:
    """Analyze data sufficiency for equipping candidate in target slot.

    Checks:
    1. Baseline presence and anchor staleness against current loadout revision.
    2. Target slot knownness in the current equipped loadout.
    3. Slot occupancy topology certainty.
    4. Build-breaker rule certainty (e.g. unknown applicability blocks confident equip).
    5. Observation state of critical baseline stats (defenses, resistances, attributes).
    """
    reasons: list[str] = []
    unobserved_facts: list[str] = []

    # 1. Slot topology and occupancy check
    is_topology_known = (
        candidate.slot_occupancy != SlotOccupancy.UNKNOWN_OCCUPANCY
        and candidate.slot_conflict_topology.is_known
    )
    if not is_topology_known:
        reasons.append(
            f"Candidate item occupancy or slot conflict topology is unknown ({candidate.slot_occupancy.value})."
        )

    # 2. Target slot knownness in loadout
    is_slot_known = False
    if loadout is not None:
        slot_entry = loadout.get_slot(slot, candidate.weapon_set)
        if slot_entry is not None:
            is_slot_known = True
        else:
            reasons.append(
                f"Target slot '{slot.value}' is unobserved or empty in loadout (revision {loadout.revision}). "
                "Current equipped item contribution cannot be compared."
            )
    else:
        reasons.append("Equipped loadout is missing or uninitialized.")

    # 3. Baseline presence and anchor staleness
    is_baseline_anchored = False
    if baseline is None:
        reasons.append("Character stat baseline is missing; absolute totals cannot be calculated.")
    else:
        if loadout is not None:
            if baseline.anchored_loadout_revision == loadout.revision:
                is_baseline_anchored = True
            else:
                reasons.append(
                    f"Baseline anchored loadout revision {baseline.anchored_loadout_revision} is stale "
                    f"compared to current loadout revision {loadout.revision}."
                )
        else:
            is_baseline_anchored = True

        # Check critical resistance facts
        res_checks = [
            ("effective_fire_res", baseline.effective_fire_res.is_known, "Fire resistance"),
            ("effective_cold_res", baseline.effective_cold_res.is_known, "Cold resistance"),
            ("effective_lightning_res", baseline.effective_lightning_res.is_known, "Lightning resistance"),
            ("effective_chaos_res", baseline.effective_chaos_res.is_known, "Chaos resistance"),
        ]
        for field_name, is_known, label in res_checks:
            if not is_known:
                unobserved_facts.append(field_name)

        # Check defensive facts
        if not baseline.life.is_known:
            unobserved_facts.append("life")

    # 4. Build-breaker safety evaluation certainty
    is_safety_verified = safety_eval.certainty == BuildBreakerCertainty.VERIFIED_SAFE
    if safety_eval.certainty == BuildBreakerCertainty.UNKNOWN_APPLICABILITY:
        reasons.append(
            f"Candidate contains modifiers with unknown applicability under build-breaker rules: {safety_eval.reason or safety_eval.rule_name}"
        )
    elif safety_eval.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER:
        reasons.append(
            f"Candidate violates verified build-breaker rule: {safety_eval.reason or safety_eval.rule_name}"
        )

    # 5. Build mechanics safety check
    is_mechanics_safe = True
    if mechanic_assessment is not None:
        mech_eval = mechanic_assessment
    elif projection is not None and hasattr(projection, "displaced_build_mechanics"):
        mech_eval = evaluate_mechanic_safety(
            displaced_modifiers=projection.displaced_build_mechanics,
            candidate_modifiers=projection.candidate_build_mechanics,
            slot=slot,
        )
    else:
        disp_mods = []
        if loadout is not None:
            slot_entry = loadout.get_slot(slot, candidate.weapon_set)
            if slot_entry and slot_entry.item:
                disp_mods = [
                    m for m in slot_entry.item.modifiers
                    if m.modifier_type == NormalizedModifierType.SPECIAL_MECHANIC
                    or m.scope.value == "BUILD_MECHANIC"
                ]
        cand_mods = [
            m for m in candidate.modifiers
            if m.modifier_type == NormalizedModifierType.SPECIAL_MECHANIC
            or m.scope.value == "BUILD_MECHANIC"
        ]
        mech_eval = evaluate_mechanic_safety(disp_mods, cand_mods, slot=slot)

    if not mech_eval.is_safe_for_equip:
        is_mechanics_safe = False
        reasons.extend(mech_eval.reasons)

    # 6. Evaluate overall sufficiency
    # Strict gate: if slot unknown, baseline missing/stale, topology unknown, build-breaker unknown/breaker,
    # or unmodeled mechanic added/removed -> INSUFFICIENT_FOR_CONFIDENT_EQUIP
    if (
        not is_slot_known
        or not is_baseline_anchored
        or not is_topology_known
        or not is_safety_verified
        or not is_mechanics_safe
        or baseline is None
    ):
        return DataSufficiencyResult(
            sufficiency=RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP,
            reasons=reasons,
            is_sufficient_for_equip_now=False,
            is_slot_known=is_slot_known,
            is_baseline_anchored=is_baseline_anchored,
            is_safety_verified=is_safety_verified,
            is_mechanics_safe=is_mechanics_safe,
            unobserved_critical_facts=unobserved_facts,
        )

    # Slot is known, baseline is anchored, topology is known, safety is verified.
    # Check if critical resistance / life facts are partially unobserved
    if unobserved_facts:
        reasons.append(
            f"Partial baseline facts observed. Unobserved critical stats: {', '.join(unobserved_facts)}."
        )
        return DataSufficiencyResult(
            sufficiency=RecommendationDataSufficiency.PARTIAL_SAFE,
            reasons=reasons,
            is_sufficient_for_equip_now=False,
            is_slot_known=is_slot_known,
            is_baseline_anchored=is_baseline_anchored,
            is_safety_verified=is_safety_verified,
            is_mechanics_safe=is_mechanics_safe,
            unobserved_critical_facts=unobserved_facts,
        )

    # All criteria satisfied
    return DataSufficiencyResult(
        sufficiency=RecommendationDataSufficiency.SUFFICIENT,
        reasons=[],
        is_sufficient_for_equip_now=True,
        is_slot_known=True,
        is_baseline_anchored=True,
        is_safety_verified=True,
        is_mechanics_safe=True,
        unobserved_critical_facts=[],
    )
