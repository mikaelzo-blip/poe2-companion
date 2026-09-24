"""Data-sufficiency analysis model for equipment intelligence recommendations."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from companion.equipment.baseline import CharacterFact, CharacterStatBaseline
from companion.equipment.fact_dependencies import (
    RecommendationFactDependencies,
    determine_recommendation_fact_dependencies,
)
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.mechanics import MechanicSafetyAssessment, evaluate_mechanic_safety
from companion.equipment.rules import BuildBreakerCertainty, BuildBreakerEvaluation
from companion.equipment.schema import (
    ItemCandidate,
    NormalizedModifierType,
    SlotOccupancy,
    SlotType,
)
from companion.state.provenance import VerificationState


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
    fact_dependencies: RecommendationFactDependencies | None = None


def analyze_data_sufficiency(
    baseline: CharacterStatBaseline | None,
    loadout: EquippedLoadout | None,
    candidate: ItemCandidate,
    slot: SlotType,
    safety_eval: BuildBreakerEvaluation,
    projection: Any = None,
    mechanic_assessment: MechanicSafetyAssessment | None = None,
    cascade_result: Any = None,
    fact_dependencies: RecommendationFactDependencies | None = None,
) -> DataSufficiencyResult:
    """Analyze data sufficiency for equipping candidate in target slot.

    Checks:
    1. Baseline presence and anchor staleness against current loadout revision.
    2. Target slot knownness in the current equipped loadout.
    3. Slot occupancy topology certainty.
    4. Build-breaker rule certainty (e.g. unknown applicability blocks confident equip).
    5. Observation state and freshness of decision-relevant baseline facts.
    """
    reasons: list[str] = []
    unobserved_facts: list[str] = []
    has_insufficient_needed_fact = False

    if fact_dependencies is None:
        fact_dependencies = determine_recommendation_fact_dependencies(
            candidate=candidate,
            loadout=loadout,
            slot=slot,
            weapon_set=candidate.weapon_set,
            cascade_result=cascade_result,
            projection=projection,
        )

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
            loadout_fp = loadout.compute_fingerprint()
            fingerprint_matches = (
                baseline.anchored_loadout_fingerprint is not None
                and baseline.anchored_loadout_fingerprint == loadout_fp
            )
            if baseline.anchored_loadout_revision == loadout.revision and fingerprint_matches:
                is_baseline_anchored = True
            else:
                if baseline.anchored_loadout_revision != loadout.revision:
                    reasons.append(
                        f"Baseline anchored loadout revision {baseline.anchored_loadout_revision} is stale "
                        f"compared to current loadout revision {loadout.revision}."
                    )
                if baseline.anchored_loadout_fingerprint is None:
                    reasons.append(
                        "Baseline lacks anchored loadout fingerprint (LEGACY_ANCHOR_REQUIRES_REBASELINE)."
                    )
                elif baseline.anchored_loadout_fingerprint != loadout_fp:
                    reasons.append(
                        f"Baseline anchored fingerprint '{baseline.anchored_loadout_fingerprint}' does not match "
                        f"current loadout fingerprint '{loadout_fp}'."
                    )
        else:
            is_baseline_anchored = True

        # Per-fact sufficiency check for decision-relevant needed facts
        needed_fact_checks = [
            (
                fact_dependencies.needs_armour,
                baseline.armour,
                "Armour",
                "this candidate changes local Armour. Exact resulting character Armour cannot be safely projected",
                "this candidate changes local Armour",
            ),
            (
                fact_dependencies.needs_evasion,
                baseline.evasion,
                "Evasion",
                "this candidate changes local Evasion. Exact resulting character Evasion cannot be safely projected",
                "this candidate changes local Evasion",
            ),
            (
                fact_dependencies.needs_energy_shield,
                baseline.energy_shield,
                "Energy Shield",
                "this candidate changes local Energy Shield. Exact resulting character Energy Shield cannot be safely projected",
                "this candidate changes local Energy Shield",
            ),
            (
                fact_dependencies.needs_movement_speed,
                baseline.movement_speed,
                "Movement Speed",
                "this swap changes Movement Speed",
                "this swap changes Movement Speed",
            ),
            (
                fact_dependencies.needs_strength,
                baseline.strength,
                "Strength",
                "is required to validate equipment/gem requirements",
                "is required to validate equipment/gem requirements",
            ),
            (
                fact_dependencies.needs_dexterity,
                baseline.dexterity,
                "Dexterity",
                "is required to validate equipment/gem requirements",
                "is required to validate equipment/gem requirements",
            ),
            (
                fact_dependencies.needs_intelligence,
                baseline.intelligence,
                "Intelligence",
                "is required to validate equipment/gem requirements",
                "is required to validate equipment/gem requirements",
            ),
            (
                fact_dependencies.needs_life,
                baseline.life,
                "Life",
                "this candidate changes Life",
                "this candidate changes Life",
            ),
            (
                fact_dependencies.needs_fire_res,
                baseline.effective_fire_res,
                "Fire Resistance",
                "this candidate changes Fire Resistance",
                "this candidate changes Fire Resistance",
            ),
            (
                fact_dependencies.needs_cold_res,
                baseline.effective_cold_res,
                "Cold Resistance",
                "this candidate changes Cold Resistance",
                "this candidate changes Cold Resistance",
            ),
            (
                fact_dependencies.needs_lightning_res,
                baseline.effective_lightning_res,
                "Lightning Resistance",
                "this candidate changes Lightning Resistance",
                "this candidate changes Lightning Resistance",
            ),
            (
                fact_dependencies.needs_chaos_res,
                baseline.effective_chaos_res,
                "Chaos Resistance",
                "this candidate changes Chaos Resistance",
                "this candidate changes Chaos Resistance",
            ),
        ]

        for is_needed, fact, stat_name, stale_suffix, other_suffix in needed_fact_checks:
            if not is_needed:
                continue
            # Optional defenses (Armour, Evasion, Energy Shield) may remain unpopulated (UNKNOWN)
            # per spec without blocking upgrades. Only STALE or CONFLICTING defenses block when changed.
            if stat_name in ("Armour", "Evasion", "Energy Shield") and fact.verification == VerificationState.UNKNOWN:
                continue
            if not fact.is_known:
                has_insufficient_needed_fact = True
                if fact.verification == VerificationState.STALE:
                    reasons.append(f"{stat_name} baseline is STALE and {stale_suffix}.")
                elif fact.verification == VerificationState.CONFLICTING:
                    reasons.append(f"{stat_name} is conflicting and {other_suffix}.")
                else:
                    reasons.append(f"{stat_name} is unknown and {other_suffix}.")

        # Check critical resistance facts
        res_checks = [
            ("effective_fire_res", baseline.effective_fire_res),
            ("effective_cold_res", baseline.effective_cold_res),
            ("effective_lightning_res", baseline.effective_lightning_res),
            ("effective_chaos_res", baseline.effective_chaos_res),
        ]
        for field_name, fact in res_checks:
            if fact.value is None or fact.verification == VerificationState.UNKNOWN:
                unobserved_facts.append(field_name)

        # Check defensive facts
        if baseline.life.value is None or baseline.life.verification == VerificationState.UNKNOWN:
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
    # unmodeled mechanic added/removed, or any needed baseline fact is missing/stale/conflicting -> INSUFFICIENT_FOR_CONFIDENT_EQUIP
    if (
        not is_slot_known
        or not is_baseline_anchored
        or not is_topology_known
        or not is_safety_verified
        or not is_mechanics_safe
        or has_insufficient_needed_fact
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
            fact_dependencies=fact_dependencies,
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
            fact_dependencies=fact_dependencies,
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
        fact_dependencies=fact_dependencies,
    )
