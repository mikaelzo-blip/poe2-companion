"""End-to-end evaluation runner and artifact persistence for objectives."""

from __future__ import annotations

import json
from pathlib import Path
import uuid
from typing import TYPE_CHECKING

from companion.build.delta import compute_build_delta
from companion.build.input import (
    BuildBrainInput,
    ObservationCoverage,
    PlayerObservationCoverage,
)
from companion.build.progression import ProgressionPhase, resolve_progression_phase
from companion.build.variants import (
    TargetVariant,
    resolve_target_variant,
)
from companion.objectives.engine import evaluate_objectives
from companion.objectives.generator import generate_objective_candidates
from companion.objectives.schema import ObjectiveEvaluationResult
from companion.rules.loader import load_guide_rules
from companion.rules.schema import GuideRule
from companion.sources.models_normalized import NormalizedBuild, normalize_build
from companion.sources.models_raw import RawBuild
from companion.transition.evaluator import evaluate_level52_transition

if TYPE_CHECKING:
    from companion.state.schema import CharacterState


def load_target_build_for_level(
    character_level: int | None,
    builds_dir: Path | str = "data/source/builds",
    selected_variant: TargetVariant | None = None,
) -> NormalizedBuild | None:
    """Find and load the normalized target build matching character progression stage."""
    lvl = character_level if character_level is not None else 1
    prog_res = resolve_progression_phase(lvl)

    if prog_res.phase == ProgressionPhase.HIGH_END:
        variant_res = resolve_target_variant(
            phase=prog_res.phase,
            selected_target_variant=selected_variant,
        )
        target_snapshot_name = variant_res.target_snapshot_name or "Endgame"
    else:
        target_snapshot_name = prog_res.target_snapshot_name

    if not target_snapshot_name:
        return None

    b_dir = Path(builds_dir)
    if not b_dir.is_dir():
        return None

    matches = [f for f in b_dir.glob("*.build") if f.name.startswith(target_snapshot_name)]
    if not matches:
        return None

    target_file = matches[0]
    with open(target_file, "r", encoding="utf-8") as f:
        raw_dict = json.load(f)
    raw = RawBuild.model_validate(raw_dict)
    return normalize_build(raw, logical_stage=target_snapshot_name)


def run_objective_pipeline(
    character_state: CharacterState,
    builds_dir: Path | str = "data/source/builds",
    rules_path: Path | str | None = None,
    rules: list[GuideRule] | None = None,
    evidence_map: dict[str, Any] | None = None,
) -> ObjectiveEvaluationResult:
    """Execute synchronous, zero-daemon objective evaluation pipeline."""
    char_lvl = character_state.level.value if character_state.level else None

    # 1. Load target build if available
    target_build = load_target_build_for_level(char_lvl, builds_dir=builds_dir)

    # 2. Compute build delta if target build is loaded
    build_delta = None
    if target_build is not None:
        passives_data = getattr(character_state, "allocated_passives", None) or getattr(character_state, "passives", None)
        skills_data = getattr(character_state, "skills", None)
        equip_data = getattr(character_state, "equipment", None)

        equip_slots = {}
        if isinstance(equip_data, dict):
            equip_slots = {slot: ObservationCoverage.COMPLETE for slot in equip_data}

        coverage = PlayerObservationCoverage(
            passives=ObservationCoverage.COMPLETE if passives_data else ObservationCoverage.UNKNOWN,
            skills=ObservationCoverage.COMPLETE if skills_data else ObservationCoverage.UNKNOWN,
            equipment_slots=equip_slots,
        )
        brain_input = BuildBrainInput(
            character_state=character_state,
            observation_coverage=coverage,
        )
        try:
            build_delta = compute_build_delta(brain_input, target_build)
        except Exception:
            build_delta = None

    # 3. Load guide rules if available
    guide_rules: list[GuideRule] | None = rules
    if guide_rules is None:
        try:
            guide_rules = load_guide_rules(rules_path)
        except Exception:
            guide_rules = None

    # 4. Evaluate M3 transition state
    try:
        transition = evaluate_level52_transition(
            character_state=character_state,
            delta=build_delta,
            rules=guide_rules,
            evidence_map=evidence_map,
        )
    except Exception:
        transition = None

    # 5. Generate candidates
    candidates = generate_objective_candidates(
        delta=build_delta,
        transition=transition,
        character_state=character_state,
        rules=guide_rules,
    )

    # 6. Rank and evaluate objectives
    return evaluate_objectives(
        character_id=character_state.character_id,
        character_level=char_lvl,
        raw_candidates=candidates,
    )


def save_current_objective_artifact(
    result: ObjectiveEvaluationResult,
    out_path: Path | str = "runtime/CURRENT_OBJECTIVE.json",
) -> Path:
    """Persist evaluated objectives atomically to disk."""
    dest = Path(out_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dest = dest.parent / f".tmp_{dest.name}_{uuid.uuid4().hex}"

    content = json.dumps(result.model_dump(), indent=2)
    tmp_dest.write_text(content, encoding="utf-8")
    tmp_dest.replace(dest)
    return dest
