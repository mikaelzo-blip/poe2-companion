"""Central EquipmentIntelligenceEngine evaluating candidates against loadout and baseline."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from companion.equipment.baseline_cli import load_baseline
from companion.equipment.baseline_gate import check_baseline_consistency
from companion.equipment.build_breaker import evaluate_candidate_build_safety
from companion.equipment.contextual_value import evaluate_loadout_contextual_analysis
from companion.equipment.data_sufficiency import analyze_data_sufficiency
from companion.equipment.fact_dependencies import (
    RecommendationFactDependencies,
    determine_recommendation_fact_dependencies,
)
from companion.equipment.loadout_cli import load_loadout
from companion.equipment.parser import parse_item_text
from companion.equipment.partial_projection import project_candidate_on_loadout
from companion.equipment.precedence import (
    MultidimensionalComparison,
    Verdict,
    evaluate_contextual_verdict,
)
from companion.equipment.recommendation import EquipmentRecommendation
from companion.equipment.requirements import GemRequirement, validate_requirement_cascades
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.schema import ItemCandidate, SlotType, WeaponSetContext


class EquipmentIntelligenceEngine:
    def __init__(self, runtime_dir: str | Path | None = None) -> None:
        self.runtime_dir = Path(runtime_dir) if runtime_dir else Path(".poe2_companion")

    def evaluate_candidate(
        self,
        item_text: str | None = None,
        character_id: str = "default",
        target_slot: str | SlotType | None = None,
        target_weapon_set: str | WeaponSetContext | None = None,
        stage: BuildProgressionStage | str = BuildProgressionStage.EARLY_ENDGAME,
        critical_gems: list[GemRequirement] | None = None,
        candidate_text: str | None = None,
        slot: str | SlotType | None = None,
        weapon_set: str | WeaponSetContext | None = None,
        build_profile: str | Any | None = None,
        resistance_policies: dict[Any, Any] | None = None,
        comparison: MultidimensionalComparison | None = None,
    ) -> EquipmentRecommendation:
        text = candidate_text if candidate_text is not None else item_text
        if text is None:
            raise ValueError("item_text or candidate_text must be provided.")

        if isinstance(stage, str):
            parsed_stage = BuildProgressionStage(stage)
            resolved_stage = parsed_stage if parsed_stage is not None else BuildProgressionStage.EARLY_ENDGAME
        elif isinstance(stage, BuildProgressionStage):
            resolved_stage = stage
        else:
            resolved_stage = BuildProgressionStage.EARLY_ENDGAME

        actual_slot = slot if slot is not None else target_slot
        if isinstance(actual_slot, str):
            res_slot = SlotType.from_str(actual_slot)
        else:
            res_slot = actual_slot

        actual_wset = weapon_set if weapon_set is not None else target_weapon_set
        if isinstance(actual_wset, str):
            res_wset = WeaponSetContext.from_val(actual_wset)
        else:
            res_wset = actual_wset

        candidate = parse_item_text(
            raw_text=text,
            target_slot=res_slot,
            target_weapon_set=res_wset,
        )
        resolved_slot = res_slot or candidate.slot
        resolved_wset = res_wset or candidate.weapon_set

        loadout = load_loadout(self.runtime_dir, character_id)
        raw_baseline = load_baseline(self.runtime_dir, character_id)

        # Baseline consistency check against loadout revision and fingerprint
        if raw_baseline is not None and loadout is not None:
            consistency_result = check_baseline_consistency(
                raw_baseline,
                current_loadout_revision=loadout.revision,
                current_loadout_fingerprint=loadout.compute_fingerprint(),
            )
            baseline = consistency_result.reconciled_baseline
        else:
            baseline = raw_baseline

        # 1. Build-breaker safety evaluation
        safety_eval = evaluate_candidate_build_safety(
            candidate=candidate,
            slot=resolved_slot,
            weapon_set=resolved_wset,
            stage=resolved_stage,
        )

        # 2. Partial projection (deltas + unverified isolation)
        projection = project_candidate_on_loadout(
            loadout=loadout,
            candidate=candidate,
            slot=resolved_slot,
            baseline=baseline,
            weapon_set=resolved_wset,
        )

        # 3. Requirement cascades
        cascade_result = validate_requirement_cascades(
            loadout=loadout,
            candidate=candidate,
            slot=resolved_slot,
            baseline=baseline,
            weapon_set=resolved_wset,
            critical_gems=critical_gems,
        )

        # 4. Data sufficiency analysis
        fact_dependencies: RecommendationFactDependencies = (
            determine_recommendation_fact_dependencies(
                candidate=candidate,
                loadout=loadout,
                slot=resolved_slot,
                weapon_set=resolved_wset,
                cascade_result=cascade_result,
                projection=projection,
            )
        )
        sufficiency = analyze_data_sufficiency(
            baseline=baseline,
            loadout=loadout,
            candidate=candidate,
            slot=resolved_slot,
            safety_eval=safety_eval,
            projection=projection,
            cascade_result=cascade_result,
            fact_dependencies=fact_dependencies,
        )

        # 5. Loadout contextual analysis (deficiencies, marginal value tiers)
        contextual_analysis = evaluate_loadout_contextual_analysis(
            baseline=baseline,
            projection=projection,
            stage=resolved_stage,
            build_profile=build_profile,
            resistance_policies=resistance_policies,
        )

        # 6. Non-scalar contextual verdict precedence & defense regression detection
        armour_delta = min(projection.local_armour_delta, int(projection.armour.delta))
        evasion_delta = min(projection.local_evasion_delta, int(projection.evasion.delta))
        es_delta = min(projection.local_energy_shield_delta, int(projection.energy_shield.delta))
        ms_delta = projection.movement_speed.delta
        life_delta = projection.life.delta
        fire_res_delta = projection.fire_res.delta
        cold_res_delta = projection.cold_res.delta
        lightning_res_delta = projection.lightning_res.delta
        chaos_res_delta = projection.chaos_res.delta

        has_defense_regression = (armour_delta < 0 or evasion_delta < 0 or es_delta < 0)
        has_ms_regression = ms_delta < 0
        has_life_regression = life_delta < 0
        has_res_regression = (
            fire_res_delta < 0 or cold_res_delta < 0 or lightning_res_delta < 0 or chaos_res_delta < 0
        )
        has_verified_regression = (
            has_defense_regression or has_ms_regression or has_life_regression or has_res_regression
        )

        has_defense_gain = (armour_delta > 0 or evasion_delta > 0 or es_delta > 0)
        has_ms_gain = ms_delta > 0
        has_life_gain = life_delta > 0
        has_res_gain = (
            fire_res_delta > 0 or cold_res_delta > 0 or lightning_res_delta > 0 or chaos_res_delta > 0
        )
        has_meaningful_gain = (
            has_defense_gain or has_ms_gain or has_life_gain or has_res_gain
        )

        equipped_entry = loadout.get_slot(resolved_slot, resolved_wset) if loadout else None
        has_equipped_item = equipped_entry is not None and equipped_entry.item is not None

        effective_comparison = comparison
        defense_tradeoff_reason = None
        downgrade_reason = None

        if effective_comparison is None:
            if has_equipped_item:
                if has_verified_regression and not has_meaningful_gain:
                    effective_comparison = MultidimensionalComparison.CLEAR_DOWNGRADE
                elif has_verified_regression and has_meaningful_gain:
                    effective_comparison = MultidimensionalComparison.MIXED_TRADEOFF
                elif not has_verified_regression and has_meaningful_gain:
                    effective_comparison = MultidimensionalComparison.DOMINANT_IMPROVEMENT
                else:
                    effective_comparison = MultidimensionalComparison.NO_MEANINGFUL_CURRENT_GAIN
            else:
                effective_comparison = (
                    MultidimensionalComparison.MIXED_TRADEOFF
                    if has_defense_regression
                    else MultidimensionalComparison.DOMINANT_IMPROVEMENT
                )

        if has_defense_regression and effective_comparison == MultidimensionalComparison.DOMINANT_IMPROVEMENT:
            effective_comparison = MultidimensionalComparison.MIXED_TRADEOFF

        if effective_comparison == MultidimensionalComparison.CLEAR_DOWNGRADE:
            loss_items = []
            if ms_delta < 0:
                loss_items.append(f"Movement Speed ({int(ms_delta):+d}%)")
            if armour_delta < 0:
                loss_items.append(f"Armour ({armour_delta:+d})")
            if evasion_delta < 0:
                loss_items.append(f"Evasion ({evasion_delta:+d})")
            if es_delta < 0:
                loss_items.append(f"Energy Shield ({es_delta:+d})")
            if life_delta < 0:
                loss_items.append(f"Life ({int(life_delta):+d})")
            if fire_res_delta < 0:
                loss_items.append(f"Fire Res ({int(fire_res_delta):+d}%)")
            if cold_res_delta < 0:
                loss_items.append(f"Cold Res ({int(cold_res_delta):+d}%)")
            if lightning_res_delta < 0:
                loss_items.append(f"Lightning Res ({int(lightning_res_delta):+d}%)")
            if chaos_res_delta < 0:
                loss_items.append(f"Chaos Res ({int(chaos_res_delta):+d}%)")

            downgrade_reason = (
                f"Candidate incurs verified item-level regressions ({', '.join(loss_items)}) "
                "with no meaningful compensating gains."
            )
            if projection.removed_build_mechanics:
                removed_names = [m.raw_text.split(" — ")[0] for m in projection.removed_build_mechanics]
                downgrade_reason += f" Additional material uncertainty: removes {', '.join(removed_names)} (unmodeled build mechanic)."

        elif effective_comparison == MultidimensionalComparison.MIXED_TRADEOFF and has_defense_regression:
            loss_parts = []
            if armour_delta < 0:
                loss_parts.append(f"Armour ({armour_delta:+d})")
            if evasion_delta < 0:
                loss_parts.append(f"Evasion ({evasion_delta:+d})")
            if es_delta < 0:
                loss_parts.append(f"Energy Shield ({es_delta:+d})")

            gain_parts = []
            if armour_delta > 0:
                gain_parts.append(f"Armour ({armour_delta:+d})")
            if evasion_delta > 0:
                gain_parts.append(f"Evasion ({evasion_delta:+d})")
            if es_delta > 0:
                gain_parts.append(f"Energy Shield ({es_delta:+d})")

            if gain_parts:
                defense_tradeoff_reason = (
                    f"Mixed defense tradeoff against equipped loadout: loses {', '.join(loss_parts)} while gaining {', '.join(gain_parts)}."
                )
            else:
                defense_tradeoff_reason = (
                    f"Candidate incurs regression on local defenses ({', '.join(loss_parts)}); represents a mixed defense tradeoff."
                )

        verdict, reason, flags = evaluate_contextual_verdict(
            safety_eval=safety_eval,
            cascade_result=cascade_result,
            contextual_analysis=contextual_analysis,
            data_sufficiency=sufficiency,
            comparison=effective_comparison,
            has_defense_regression=has_defense_regression,
            defense_tradeoff_reason=defense_tradeoff_reason,
            downgrade_reason=downgrade_reason,
        )

        # 7. Actionable guidance
        guidance: list[str] = []
        if verdict == Verdict.EQUIP_NOW:
            guidance.append(f"Safe direct upgrade. Promote via 'companion gear loadout promote-candidate --slot {resolved_slot.value}'.")
            if contextual_analysis and contextual_analysis.has_unresolved_resistance_priority:
                guidance.append("Unresolved campaign resistance priorities: seek additional resistance on other gear slots.")
        elif verdict == Verdict.CONDITIONAL_UPGRADE:
            if "MIXED_TRADEOFF" in flags:
                guidance.append("Evaluate defense trade-offs against offensive or utility gains before equipping.")
            if "REQUIREMENT_DEFICIENCY" in flags or "UNMITIGATED_DEFICIT" in flags or "MIXED_TRADEOFF" not in flags:
                guidance.append("Solve requirement/resistance deficits elsewhere before equipping.")
        elif verdict == Verdict.KEEP_FOR_LATER:
            guidance.append("Keep in stash for future gear reshuffling.")
        elif verdict == Verdict.REJECT:
            guidance.append("Do not equip: harms character progression or violates build mechanics.")
        elif verdict == Verdict.INSUFFICIENT_DATA:
            guidance.append("Capture missing baseline or loadout facts before making equip decision.")

        return EquipmentRecommendation(
            character_id=character_id,
            slot=resolved_slot,
            target_weapon_set=resolved_wset,
            candidate=candidate,
            displaced_items=projection.displaced_items,
            projection=projection,
            safety_eval=safety_eval,
            cascade_result=cascade_result,
            verdict=verdict,
            verdict_reason=reason,
            flags=flags,
            sufficiency=sufficiency,
            contextual_analysis=contextual_analysis,
            actionable_guidance=guidance,
        )
