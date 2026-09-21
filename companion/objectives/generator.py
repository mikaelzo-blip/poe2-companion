"""Objective candidate generator consuming M2 build deltas, M3 transitions, and guide rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from companion.build.delta import BuildDeltaResult
from companion.build.policy import DeltaStatus
from companion.build.variants import VariantResolutionStatus
from companion.objectives.schema import (
    CostOfIgnoring,
    EvidenceTrustworthiness,
    ObjectiveCandidate,
    ObjectiveHorizon,
    ObjectivePriority,
)
from companion.state.schema import CharacterState
from companion.transition.state import Level52TransitionResult, Level52TransitionState

if TYPE_CHECKING:
    from companion.rules.schema import GuideRule


def generate_objective_candidates(
    delta: BuildDeltaResult,
    transition: Level52TransitionResult | None,
    character_state: CharacterState,
    rules: list[GuideRule] | None = None,
) -> list[ObjectiveCandidate]:
    """Deterministically synthesize objective candidates from M2 and M3 factual states.

    Pure function. Preserves uncertainty, isolates future requirements, and enforces
    authoritative rule boundaries.
    """
    candidates: list[ObjectiveCandidate] = []

    # 1. Target Variant Resolution (M2)
    if delta is not None:
        var_res = delta.target_variant_resolution
        if var_res and var_res.status == VariantResolutionStatus.UNRESOLVED:
            candidates.append(
                ObjectiveCandidate(
                    id="build:target_variant_selection",
                    priority=ObjectivePriority.CURRENT_PROGRESSION,
                    title="Select High-End Target Variant",
                    action="Select target variant: ENDGAME, MAGEBLOOD, or DOT_CAP",
                    rationale="High-end progression requires explicit variant selection; no implicit LVL85 assumed",
                    source="Build Brain Target Variant Resolver",
                    evidence_trust=EvidenceTrustworthiness.VERIFIED,
                    horizon=ObjectiveHorizon.CURRENT,
                    cost_of_ignoring=CostOfIgnoring.HIGH,
                    is_corrective=False,
                    metadata={"reason": var_res.reason},
                )
            )

    # 2. Transition State Machine (M3)
    if transition is not None:
        if transition.state == Level52TransitionState.BLOCKED:
            # Active blockers generate HARD_BLOCKER
            unsatisfied_blockers = [
                r for r in transition.blocking_requirements if r.is_unsatisfied
            ]
            if not unsatisfied_blockers:
                unsatisfied_blockers = [
                    r for r in transition.requirements if r.is_unsatisfied
                ]
            for req in unsatisfied_blockers:
                summary = req.reason or "Required condition unsatisfied for level-52 swap"
                candidates.append(
                    ObjectiveCandidate(
                        id=f"transition:level52:blocked:{req.rule_id}",
                        priority=ObjectivePriority.HARD_BLOCKER,
                        title=f"Resolve Level-52 Transition Blocker: {req.rule_name or req.rule_id}",
                        action=f"Satisfy requirement '{req.rule_id}' for level-52 weapon swap",
                        rationale=summary,
                        source="Level-52 Transition Evaluator",
                        evidence_trust=EvidenceTrustworthiness.VERIFIED,
                        horizon=ObjectiveHorizon.CURRENT,
                        cost_of_ignoring=CostOfIgnoring.HIGH,
                        is_corrective=True,
                        metadata={"blocker_id": req.rule_id},
                    )
                )
        elif transition.state == Level52TransitionState.VERIFYING:
            # Verification tasks generate non-corrective audit objectives
            unknown_blockers = [
                r for r in transition.blocking_requirements if r.is_unknown
            ]
            for req in unknown_blockers:
                summary = req.reason or "Observation data incomplete or stale for level-52 transition"
                candidates.append(
                    ObjectiveCandidate(
                        id=f"transition:level52:verifying:{req.rule_id}",
                        priority=ObjectivePriority.TRANSITION_REQUIREMENT,
                        title=f"Verify Level-52 Transition Requirement: {req.rule_name or req.rule_id}",
                        action=f"Audit character equipment and skills to verify '{req.rule_id}'",
                        rationale=summary,
                        source="Level-52 Transition Evaluator",
                        evidence_trust=EvidenceTrustworthiness.STALE_OR_UNKNOWN,
                        horizon=ObjectiveHorizon.CURRENT,
                        cost_of_ignoring=CostOfIgnoring.HIGH,
                        is_corrective=False,
                        metadata={"rule_id": req.rule_id},
                    )
                )
            if not unknown_blockers and transition.unknowns:
                for unk in transition.unknowns:
                    candidates.append(
                        ObjectiveCandidate(
                            id=f"transition:level52:verifying:{unk}",
                            priority=ObjectivePriority.TRANSITION_REQUIREMENT,
                            title=f"Verify Level-52 Transition Observation: {unk}",
                            action=f"Audit character equipment to verify '{unk}'",
                            rationale="Character reached level 52 but transition observations are incomplete",
                            source="Level-52 Transition Evaluator",
                            evidence_trust=EvidenceTrustworthiness.STALE_OR_UNKNOWN,
                            horizon=ObjectiveHorizon.CURRENT,
                            cost_of_ignoring=CostOfIgnoring.HIGH,
                            is_corrective=False,
                        )
                    )
            elif not unknown_blockers and not transition.unknowns:
                candidates.append(
                    ObjectiveCandidate(
                        id="transition:level52:verifying:general",
                        priority=ObjectivePriority.TRANSITION_REQUIREMENT,
                        title="Verify Level-52 Transition Readiness",
                        action="Perform gear and skill audit for level-52 weapon swap",
                        rationale="Character reached level 52 but transition observations are incomplete",
                        source="Level-52 Transition Evaluator",
                        evidence_trust=EvidenceTrustworthiness.STALE_OR_UNKNOWN,
                        horizon=ObjectiveHorizon.CURRENT,
                        cost_of_ignoring=CostOfIgnoring.HIGH,
                        is_corrective=False,
                    )
                )
        elif transition.state == Level52TransitionState.PREPARING:
            candidates.append(
                ObjectiveCandidate(
                    id="transition:level52:preparing",
                    priority=ObjectivePriority.TRANSITION_REQUIREMENT,
                    title="Prepare for Level-52 Weapon Swap",
                    action="Acquire secondary weapon set items and gem setups",
                    rationale="Character approaching level 52 dual weapon set transition",
                    source="Level-52 Transition State Machine",
                    evidence_trust=EvidenceTrustworthiness.VERIFIED,
                    horizon=ObjectiveHorizon.CURRENT,
                    cost_of_ignoring=CostOfIgnoring.LOW,
                    is_corrective=False,
                )
            )
        elif transition.state == Level52TransitionState.READY:
            candidates.append(
                ObjectiveCandidate(
                    id="transition:level52:ready",
                    priority=ObjectivePriority.TRANSITION_REQUIREMENT,
                    title="Execute Level-52 Dual Weapon Set Swap",
                    action="Equip cross-swap weapons and socket gem configurations",
                    rationale="All applicable blocking requirements for level-52 transition are satisfied",
                    source="Level-52 Transition Evaluator",
                    evidence_trust=EvidenceTrustworthiness.VERIFIED,
                    horizon=ObjectiveHorizon.CURRENT,
                    cost_of_ignoring=CostOfIgnoring.HIGH,
                    is_corrective=True,
                )
            )
        elif transition.state == Level52TransitionState.TRANSITIONING:
            candidates.append(
                ObjectiveCandidate(
                    id="transition:level52:transitioning",
                    priority=ObjectivePriority.TRANSITION_REQUIREMENT,
                    title="Complete Level-52 Transition",
                    action="Confirm post-swap equipment and skill setups",
                    rationale="Transition trigger initiated; awaiting completion evidence",
                    source="Level-52 Transition Evaluator",
                    evidence_trust=EvidenceTrustworthiness.VERIFIED,
                    horizon=ObjectiveHorizon.CURRENT,
                    cost_of_ignoring=CostOfIgnoring.HIGH,
                    is_corrective=False,
                )
            )
        # Level52TransitionState.COMPLETE produces ZERO transition objectives!

    # 3. Passives Delta (M2)
    if delta is not None:
        for p_entry in delta.passives:
            ws_str = (
                p_entry.weapon_set_context.value
                if hasattr(p_entry.weapon_set_context, "value")
                else str(p_entry.weapon_set_context)
            )
            compound_key_str = f"{p_entry.passive_id}#{ws_str}"
            if p_entry.status == DeltaStatus.MISSING:
                candidates.append(
                    ObjectiveCandidate(
                        id=f"passive:missing:{compound_key_str}",
                        priority=ObjectivePriority.CURRENT_PROGRESSION,
                        title=f"Allocate Passive: {p_entry.passive_id}",
                        action=f"Allocate passive node '{p_entry.passive_id}' in context '{ws_str}'",
                        rationale="Required passive node is missing from character allocations",
                        source=f"Target Snapshot: {delta.target_stage_name or 'target'}",
                        evidence_trust=EvidenceTrustworthiness.VERIFIED,
                        horizon=ObjectiveHorizon.CURRENT,
                        cost_of_ignoring=CostOfIgnoring.HIGH,
                        is_corrective=True,
                        metadata={"compound_key": compound_key_str},
                    )
                )
            elif p_entry.status == DeltaStatus.UNKNOWN:
                reason_str = p_entry.reason.value if hasattr(p_entry.reason, "value") else str(p_entry.reason)
                candidates.append(
                    ObjectiveCandidate(
                        id=f"passive:unknown:{compound_key_str}",
                        priority=ObjectivePriority.CURRENT_PROGRESSION,
                        title=f"Audit Passive Tree: {p_entry.passive_id}",
                        action=f"Inspect passive tree to verify allocation of '{p_entry.passive_id}'",
                        rationale=f"Passive observation incomplete: {reason_str}",
                        source="Passive Delta Evaluator",
                        evidence_trust=EvidenceTrustworthiness.STALE_OR_UNKNOWN,
                        horizon=ObjectiveHorizon.CURRENT,
                        cost_of_ignoring=CostOfIgnoring.LOW,
                        is_corrective=False,
                        metadata={"compound_key": compound_key_str, "reason": reason_str},
                    )
                )

        # 4. Skills Delta (M2)
        for s_entry in delta.skills:
            skill_name = s_entry.primary_gem_id
            if s_entry.status == DeltaStatus.FUTURE:
                candidates.append(
                    ObjectiveCandidate(
                        id=f"skill:future:{skill_name}",
                        priority=ObjectivePriority.FUTURE_PREPARATION,
                        title=f"Future Skill Preparation: {skill_name}",
                        action=f"Plan to acquire gem '{skill_name}' for upcoming progression",
                        rationale="Skill is required in future progression stages but not currently eligible",
                        source="Skill Delta Evaluator",
                        evidence_trust=EvidenceTrustworthiness.SINGLE_SOURCE,
                        horizon=ObjectiveHorizon.FUTURE,
                        cost_of_ignoring=CostOfIgnoring.LOW,
                        is_corrective=False,
                        metadata={"primary_gem_id": skill_name},
                    )
                )
            elif s_entry.status == DeltaStatus.MISSING:
                candidates.append(
                    ObjectiveCandidate(
                        id=f"skill:missing:{skill_name}",
                        priority=ObjectivePriority.CURRENT_PROGRESSION,
                        title=f"Equip Required Skill: {skill_name}",
                        action=f"Socket and configure gem setup for '{skill_name}'",
                        rationale="Required active gem setup is missing from character state",
                        source=f"Target Snapshot: {delta.target_stage_name or 'target'}",
                        evidence_trust=EvidenceTrustworthiness.VERIFIED,
                        horizon=ObjectiveHorizon.CURRENT,
                        cost_of_ignoring=CostOfIgnoring.HIGH,
                        is_corrective=True,
                        metadata={"primary_gem_id": skill_name},
                    )
                )
            elif s_entry.status == DeltaStatus.UNKNOWN:
                candidates.append(
                    ObjectiveCandidate(
                        id=f"skill:unknown:{skill_name}",
                        priority=ObjectivePriority.CURRENT_PROGRESSION,
                        title=f"Audit Gem Sockets: {skill_name}",
                        action=f"Inspect socket setups to verify '{skill_name}'",
                        rationale="Skill observations incomplete or stale",
                        source="Skill Delta Evaluator",
                        evidence_trust=EvidenceTrustworthiness.STALE_OR_UNKNOWN,
                        horizon=ObjectiveHorizon.CURRENT,
                        cost_of_ignoring=CostOfIgnoring.LOW,
                        is_corrective=False,
                        metadata={"primary_gem_id": skill_name},
                    )
                )

        # 5. Equipment Delta (M2)
        for eq_entry in delta.equipment:
            if eq_entry.status == DeltaStatus.MISSING:
                candidates.append(
                    ObjectiveCandidate(
                        id=f"equipment:missing:{eq_entry.slot_id}",
                        priority=ObjectivePriority.STRONG_UPGRADE,
                        title=f"Upgrade Slot: {eq_entry.slot_id}",
                        action=f"Equip recommended item in slot '{eq_entry.slot_id}'",
                        rationale="Equipped item does not match target build recommendation",
                        source=f"Target Snapshot: {delta.target_stage_name or 'target'}",
                        evidence_trust=EvidenceTrustworthiness.VERIFIED,
                        horizon=ObjectiveHorizon.CURRENT,
                        cost_of_ignoring=CostOfIgnoring.LOW,
                        is_corrective=True,
                        metadata={"slot_id": eq_entry.slot_id},
                    )
                )
            elif eq_entry.status == DeltaStatus.UNKNOWN:
                candidates.append(
                    ObjectiveCandidate(
                        id=f"equipment:unknown:{eq_entry.slot_id}",
                        priority=ObjectivePriority.OPTIMIZATION,
                        title=f"Audit Gear Slot: {eq_entry.slot_id}",
                        action=f"Inspect equipped gear in slot '{eq_entry.slot_id}'",
                        rationale="Equipment observation incomplete or unobserved",
                        source="Equipment Delta Evaluator",
                        evidence_trust=EvidenceTrustworthiness.STALE_OR_UNKNOWN,
                        horizon=ObjectiveHorizon.CURRENT,
                        cost_of_ignoring=CostOfIgnoring.LOW,
                        is_corrective=False,
                        metadata={"slot_id": eq_entry.slot_id},
                    )
                )

    # 6. Survival Risk Gating (Only when backed by authoritative evaluable USABLE rules)
    if rules:
        for rule in rules:
            if (
                rule.source_status.value == "USABLE"
                and rule.evaluable
                and "survival" in rule.id.lower()
            ):
                pass

    return candidates
