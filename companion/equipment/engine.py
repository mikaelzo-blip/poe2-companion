"""Central EquipmentIntelligenceEngine evaluating candidates against loadout and baseline."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from companion.equipment.baseline_cli import load_baseline
from companion.equipment.baseline_gate import check_baseline_consistency
from companion.equipment.build_breaker import evaluate_candidate_build_safety
from companion.equipment.contextual_value import evaluate_loadout_contextual_analysis
from companion.equipment.data_sufficiency import analyze_data_sufficiency
from companion.equipment.loadout_cli import load_loadout
from companion.equipment.parser import parse_item_text
from companion.equipment.partial_projection import project_candidate_on_loadout
from companion.equipment.precedence import Verdict, evaluate_contextual_verdict
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
        raw_baseline = load_baseline(self.runtime_dir, character_id)

        # Baseline consistency check against loadout revision
        if raw_baseline is not None and loadout is not None:
            consistency_result = check_baseline_consistency(raw_baseline, loadout.revision)
            baseline = consistency_result.reconciled_baseline
        else:
            baseline = raw_baseline

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

        # 4. Data sufficiency analysis
        sufficiency = analyze_data_sufficiency(
            baseline=baseline,
            loadout=loadout,
            candidate=candidate,
            slot=resolved_slot,
            safety_eval=safety_eval,
            projection=projection,
        )

        # 5. Loadout contextual analysis (deficiencies, marginal value tiers)
        contextual_analysis = evaluate_loadout_contextual_analysis(
            baseline=baseline,
            projection=projection,
        )

        # 6. Non-scalar contextual verdict precedence
        verdict, reason, flags = evaluate_contextual_verdict(
            safety_eval=safety_eval,
            cascade_result=cascade_result,
            contextual_analysis=contextual_analysis,
            data_sufficiency=sufficiency,
        )

        # 7. Actionable guidance
        guidance: list[str] = []
        if verdict == Verdict.EQUIP_NOW:
            guidance.append(f"Safe direct upgrade. Promote via 'companion gear loadout promote-candidate --slot {resolved_slot.value}'.")
        elif verdict == Verdict.CONDITIONAL_UPGRADE:
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
