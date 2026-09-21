"""Root BuildDeltaResult contract and M2 offline Build Brain delta orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING
from pydantic import BaseModel, ConfigDict, Field

from companion.build.conflicts import ConflictRecord
from companion.build.equipment import EquipmentDeltaEntry, evaluate_equipment_delta
from companion.build.input import BuildBrainInput, ObservationCoverage
from companion.build.passives import (
    PassiveDeltaEntry,
    canonicalize_target_passives,
    evaluate_passive_delta,
)
from companion.build.policy import DeltaStatus
from companion.build.progression import ProgressionPhase, resolve_progression_phase
from companion.build.skills import (
    SkillGroupDeltaEntry,
    canonicalize_target_skills,
    evaluate_skill_delta,
)
from companion.build.validation import validate_character_level
from companion.build.variants import (
    TargetVariantResolution,
    VariantResolutionStatus,
    resolve_target_variant,
)

if TYPE_CHECKING:
    from companion.sources.models_normalized import NormalizedBuild


class BuildDeltaResult(BaseModel):
    """Deterministic, structured delta result between character state and build target."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    character_id: str
    character_level: int | None
    progression_phase: ProgressionPhase
    target_variant_resolution: TargetVariantResolution
    target_stage_name: str | None
    target_manifest_sha256: str | None = None

    passives: list[PassiveDeltaEntry] = Field(default_factory=list)
    skills: list[SkillGroupDeltaEntry] = Field(default_factory=list)
    equipment: list[EquipmentDeltaEntry] = Field(default_factory=list)

    conflicts: list[ConflictRecord] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    is_fully_audited: bool = False


def compute_build_delta(
    brain_input: BuildBrainInput,
    target_build: NormalizedBuild,
    manifest_sha256: str | None = None,
) -> BuildDeltaResult:
    """Compute structured factual deltas between character state and normalized target build.

    Pure, deterministic, side-effect free offline evaluator.
    No live sensors, no notifications, no objective ranking, no M3 transition machines.
    """
    char_state = brain_input.character_state
    char_level_raw = char_state.level.value if char_state.level else None
    char_level = validate_character_level(char_level_raw)

    # 1. Resolve Progression Phase
    prog_res = resolve_progression_phase(char_level)

    # 2. Resolve High-End Target Variant
    variant_res = resolve_target_variant(
        phase=prog_res.phase,
        selected_target_variant=brain_input.selected_target_variant,
    )

    # 3. Determine target stage name
    if prog_res.phase == ProgressionPhase.HIGH_END:
        target_stage_name = variant_res.target_snapshot_name
    else:
        target_stage_name = prog_res.target_snapshot_name

    # 4. Passives canonicalization and delta
    canonical_passives, passive_conflicts = canonicalize_target_passives(
        target_build.passives,
        source_provenance=target_build.logical_stage,
    )
    passives_delta = evaluate_passive_delta(
        target_passives=canonical_passives,
        character_state=char_state,
        coverage=brain_input.observation_coverage.passives,
    )

    # 5. Skills canonicalization and delta
    canonical_skills = canonicalize_target_skills(
        target_build.skills,
        source_provenance=target_build.logical_stage,
    )
    skills_delta = evaluate_skill_delta(
        target_skills=canonical_skills,
        character_state=char_state,
        coverage=brain_input.observation_coverage.skills,
        character_level=char_level,
    )

    # 6. Equipment delta
    equipment_delta = evaluate_equipment_delta(
        target_slots=target_build.inventory_slots,
        character_state=char_state,
        coverage_map=brain_input.observation_coverage.equipment_slots,
        character_level=char_level,
    )

    # 7. Aggregate conflicts and unknowns
    all_conflicts = list(passive_conflicts)
    unknowns: list[str] = []

    for p in passives_delta:
        if p.status == DeltaStatus.UNKNOWN:
            unknowns.append(f"passive:{p.passive_id}:{p.weapon_set_context.value}:{p.reason.value}")
    for s in skills_delta:
        if s.status == DeltaStatus.UNKNOWN:
            unknowns.append(f"skill:{s.primary_gem_id}:{s.reason.value}")
    for e in equipment_delta:
        if e.status == DeltaStatus.UNKNOWN:
            unknowns.append(f"equipment:{e.slot_id}:{e.reason.value}")

    # 8. Check if fully audited
    passives_complete = brain_input.observation_coverage.passives == ObservationCoverage.COMPLETE
    skills_complete = brain_input.observation_coverage.skills == ObservationCoverage.COMPLETE
    eq_slots_complete = True
    if target_build.inventory_slots:
        for slot in target_build.inventory_slots:
            cov = brain_input.observation_coverage.equipment_slots.get(
                slot.inventory_id, ObservationCoverage.UNKNOWN
            )
            if cov != ObservationCoverage.COMPLETE:
                eq_slots_complete = False
                break

    is_fully_audited = (
        passives_complete
        and skills_complete
        and eq_slots_complete
        and len(unknowns) == 0
    )

    return BuildDeltaResult(
        character_id=char_state.character_id,
        character_level=char_level,
        progression_phase=prog_res.phase,
        target_variant_resolution=variant_res,
        target_stage_name=target_stage_name,
        target_manifest_sha256=manifest_sha256,
        passives=passives_delta,
        skills=skills_delta,
        equipment=equipment_delta,
        conflicts=all_conflicts,
        unknowns=unknowns,
        is_fully_audited=is_fully_audited,
    )
