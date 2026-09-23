"""Central EquipmentIntelligenceEngine evaluating candidates against loadout and baseline."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from companion.equipment.baseline_cli import load_baseline
from companion.equipment.build_breaker import evaluate_candidate_build_safety
from companion.equipment.loadout_cli import load_loadout
from companion.equipment.parser import parse_item_text
from companion.equipment.partial_projection import project_candidate_on_loadout
from companion.equipment.precedence import Verdict, evaluate_verdict_precedence
from companion.equipment.recommendation import EquipmentRecommendation
from companion.equipment.requirements import GemRequirement, validate_requirement_cascades
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.schema import ItemCandidate, SlotType, WeaponSetContext
from companion.equipment.slots import get_slot_weights


class EquipmentIntelligenceEngine:
    def __init__(self, runtime_dir: str | Path | None = None) -> None:
        self.runtime_dir = Path(runtime_dir) if runtime_dir else Path(".poe2_companion")

    def evaluate_candidate(
        self,
        item_text: str | None = None,
        character_id: str = "default",
        target_slot: str | SlotType | None = None,
        target_weapon_set: str | WeaponSetContext | None = None,
        stage: BuildProgressionStage = BuildProgressionStage.EARLY_ENDGAME,
        critical_gems: list[GemRequirement] | None = None,
        candidate_text: str | None = None,
        slot: str | SlotType | None = None,
        weapon_set: str | WeaponSetContext | None = None,
    ) -> EquipmentRecommendation:
        text = candidate_text if candidate_text is not None else item_text
        if text is None:
            raise ValueError("item_text or candidate_text must be provided.")

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
        baseline = load_baseline(self.runtime_dir, character_id)

        # 1. Build-breaker safety evaluation
        safety_eval = evaluate_candidate_build_safety(
            candidate=candidate,
            slot=resolved_slot,
            weapon_set=resolved_wset,
            stage=stage,
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

        # 4. Score delta calculation using slot weights
        weights = get_slot_weights(resolved_slot)
        score_delta = 0.0
        score_delta += projection.life.delta * weights.life_weight
        score_delta += (
            projection.fire_res.delta
            + projection.cold_res.delta
            + projection.lightning_res.delta
            + projection.chaos_res.delta
        ) * weights.res_weight
        score_delta += projection.movement_speed.delta * weights.movement_speed_weight
        score_delta += (
            projection.local_armour_delta
            + projection.local_evasion_delta
            + projection.local_energy_shield_delta
        ) * weights.defense_weight
        score_delta += (
            projection.strength.delta
            + projection.dexterity.delta
            + projection.intelligence.delta
        ) * weights.attribute_weight

        # Check for unmitigated resistance deficits
        unmitigated_deficit = False
        for res_proj in (projection.fire_res, projection.cold_res, projection.lightning_res):
            if res_proj.projected_absolute is not None and res_proj.projected_absolute < 75:
                if res_proj.delta < 0:
                    unmitigated_deficit = True

        # 5. Non-scalar verdict precedence
        verdict, reason, flags = evaluate_verdict_precedence(
            score_delta=score_delta,
            safety_eval=safety_eval,
            cascade_result=cascade_result,
            unmitigated_resistance_deficit=unmitigated_deficit,
        )

        # 6. Actionable guidance
        guidance: list[str] = []
        if verdict == Verdict.EQUIP_NOW:
            guidance.append(f"Safe direct upgrade. Promote via 'companion gear loadout promote-candidate --slot {resolved_slot.value}'.")
        elif verdict == Verdict.CONDITIONAL_UPGRADE:
            guidance.append("Solve requirement/resistance deficits elsewhere before equipping.")
        elif verdict == Verdict.STASH_FOR_LATER:
            guidance.append("Keep in stash for future gear reshuffling.")
        elif verdict == Verdict.REJECT:
            guidance.append("Do not equip: harms character progression or violates build mechanics.")

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
            score_delta=score_delta,
            actionable_guidance=guidance,
        )
