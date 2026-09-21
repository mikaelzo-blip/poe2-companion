"""Comprehensive golden scenario test suite exercising end-to-end evaluation against real M0 Fubgun snapshots."""

import json
from pathlib import Path
import pytest
from companion.sources.models_raw import RawBuild
from companion.sources.models_normalized import normalize_build
from companion.state.provenance import VerificationState
from companion.state.schema import CharacterState
from companion.build.input import (
    BuildBrainInput,
    ObservationCoverage,
    PlayerObservationCoverage,
)
from companion.build.progression import ProgressionPhase, resolve_progression_phase
from companion.build.variants import (
    TargetVariant,
    TargetVariantResolution,
    VariantResolutionStatus,
    resolve_target_variant,
)
from companion.build.policy import DeltaReason, DeltaStatus
from companion.build.delta import BuildDeltaResult, compute_build_delta


def _load_build(filename: str, logical_stage: str):
    path = Path("data/source/builds") / filename
    with open(path, "r", encoding="utf-8") as f:
        raw_dict = json.load(f)
    raw = RawBuild.model_validate(raw_dict)
    return normalize_build(raw, logical_stage=logical_stage)


@pytest.fixture(scope="module")
def real_builds():
    return {
        "lvl 1-14": _load_build("lvl 1-14 - 0.5.5 Fubgun Flameblast Oil G.build", "lvl 1-14"),
        "lvl 15-32": _load_build("lvl 15-32 - 0.5.5 Fubgun Flameblast Oil.build", "lvl 15-32"),
        "lvl 33-51": _load_build("lvl 33-51 - 0.5.5 Fubgun Flameblast Oil.build", "lvl 33-51"),
        "lvl 52 Swap": _load_build("lvl 52 Swap - 0.5.5 Fubgun Flameblast Oi.build", "lvl 52 Swap"),
        "lvl 53-68": _load_build("lvl 53-68 - 0.5.5 Fubgun Flameblast Oil.build", "lvl 53-68"),
        "lvl 85": _load_build("lvl 85 - 0.5.5 Fubgun Flameblast Oil Gre.build", "lvl 85"),
        "Endgame": _load_build("Endgame - 0.5.5 Fubgun Flameblast Oil Gr.build", "Endgame"),
        "Mageblood": _load_build("Mageblood - 0.5.5 Fubgun Flameblast Oil.build", "Mageblood"),
        "DoT Cap": _load_build("DoT Cap - 0.5.5 Fubgun Flameblast Oil Gr.build", "DoT Cap"),
    }


def test_golden_progression_across_all_key_levels(real_builds) -> None:
    """Verify progression phase and snapshot mapping across levels: 1, 14, 15, 32, 33, 51, 52, 53, 58, 68, 69, 84, 85."""
    level_expectations = [
        (1, ProgressionPhase.LEVELING_1_14, "lvl 1-14", "CANONICAL_UPSTREAM_SNAPSHOT"),
        (14, ProgressionPhase.LEVELING_1_14, "lvl 1-14", "CANONICAL_UPSTREAM_SNAPSHOT"),
        (15, ProgressionPhase.LEVELING_15_32, "lvl 15-32", "CANONICAL_UPSTREAM_SNAPSHOT"),
        (32, ProgressionPhase.LEVELING_15_32, "lvl 15-32", "CANONICAL_UPSTREAM_SNAPSHOT"),
        (33, ProgressionPhase.LEVELING_33_51, "lvl 33-51", "CANONICAL_UPSTREAM_SNAPSHOT"),
        (51, ProgressionPhase.LEVELING_33_51, "lvl 33-51", "CANONICAL_UPSTREAM_SNAPSHOT"),
        (52, ProgressionPhase.POST_52_53_68, "lvl 53-68", "CANONICAL_UPSTREAM_SNAPSHOT"),
        (53, ProgressionPhase.POST_52_53_68, "lvl 53-68", "CANONICAL_UPSTREAM_SNAPSHOT"),
        (58, ProgressionPhase.POST_52_53_68, "lvl 53-68", "CANONICAL_UPSTREAM_SNAPSHOT"),
        (68, ProgressionPhase.POST_52_53_68, "lvl 53-68", "CANONICAL_UPSTREAM_SNAPSHOT"),
        (69, ProgressionPhase.LEVELING_69_84_FALLBACK, "lvl 53-68", "COMPANION_FALLBACK_SOURCE_GAP"),
        (84, ProgressionPhase.LEVELING_69_84_FALLBACK, "lvl 53-68", "COMPANION_FALLBACK_SOURCE_GAP"),
        (85, ProgressionPhase.HIGH_END, None, "REQUIRES_HIGH_END_VARIANT"),
    ]

    for lvl, exp_phase, exp_snapshot, exp_prov in level_expectations:
        res = resolve_progression_phase(lvl)
        assert res.phase == exp_phase, f"Level {lvl} expected {exp_phase}, got {res.phase}"
        assert res.target_snapshot_name == exp_snapshot, f"Level {lvl} expected {exp_snapshot}, got {res.target_snapshot_name}"
        assert res.provenance == exp_prov, f"Level {lvl} expected {exp_prov}, got {res.provenance}"


def test_golden_high_end_variant_resolutions() -> None:
    """Verify explicit high-end variant resolutions and unresolved state when None."""
    # 1. None returns UNRESOLVED (never LVL85 default)
    res_none = resolve_target_variant(ProgressionPhase.HIGH_END, None)
    assert res_none.status == VariantResolutionStatus.UNRESOLVED
    assert res_none.variant is None
    assert res_none.reason == "NO_EXPLICIT_HIGH_END_VARIANT"

    # 2. LVL85
    res_85 = resolve_target_variant(ProgressionPhase.HIGH_END, TargetVariant.LVL85)
    assert res_85.status == VariantResolutionStatus.RESOLVED
    assert res_85.variant == TargetVariant.LVL85
    assert res_85.target_snapshot_name == "lvl 85"

    # 3. ENDGAME
    res_end = resolve_target_variant(ProgressionPhase.HIGH_END, TargetVariant.ENDGAME)
    assert res_end.status == VariantResolutionStatus.RESOLVED
    assert res_end.variant == TargetVariant.ENDGAME
    assert res_end.target_snapshot_name == "Endgame"

    # 4. MAGEBLOOD
    res_mb = resolve_target_variant(ProgressionPhase.HIGH_END, TargetVariant.MAGEBLOOD)
    assert res_mb.status == VariantResolutionStatus.RESOLVED
    assert res_mb.variant == TargetVariant.MAGEBLOOD
    assert res_mb.target_snapshot_name == "Mageblood"

    # 5. DOT_CAP
    res_dot = resolve_target_variant(ProgressionPhase.HIGH_END, TargetVariant.DOT_CAP)
    assert res_dot.status == VariantResolutionStatus.RESOLVED
    assert res_dot.variant == TargetVariant.DOT_CAP
    assert res_dot.target_snapshot_name == "DoT Cap"


def test_golden_unobserved_player_state_produces_zero_missing(real_builds) -> None:
    """A completely unobserved character state must evaluate to UNKNOWN or FUTURE with ZERO MISSING items."""
    char = CharacterState.create_initial("clean_hero", "CleanHero")
    target_build = real_builds["lvl 1-14"]

    brain_input = BuildBrainInput(
        character_state=char,
        observation_coverage=PlayerObservationCoverage(),  # Default UNKNOWN coverage
        selected_target_variant=None,
    )

    result = compute_build_delta(brain_input, target_build)

    assert result.character_id == "clean_hero"
    assert result.progression_phase == ProgressionPhase.LEVELING_1_14
    assert result.target_stage_name == "lvl 1-14"

    # ZERO items may be MISSING
    for p in result.passives:
        assert p.status != DeltaStatus.MISSING, f"Passive {p.passive_id} should not be MISSING in unobserved state"
        assert p.status in (DeltaStatus.UNKNOWN, DeltaStatus.FUTURE)

    for s in result.skills:
        assert s.status != DeltaStatus.MISSING, f"Skill {s.primary_gem_id} should not be MISSING in unobserved state"
        assert s.status in (DeltaStatus.UNKNOWN, DeltaStatus.FUTURE)

    for e in result.equipment:
        assert e.status != DeltaStatus.MISSING, f"Equipment slot {e.slot_id} should not be MISSING in unobserved state"
        assert e.status in (DeltaStatus.UNKNOWN, DeltaStatus.FUTURE)


def test_golden_partial_audit_produces_unknown_never_missing(real_builds) -> None:
    """A verified player state with PARTIAL coverage must evaluate absent items to UNKNOWN, never MISSING."""
    char = CharacterState.create_initial("partial_hero", "PartialHero")
    char = char.model_copy(update={"level": char.level.with_update(10, "TEST", VerificationState.VERIFIED)})
    char.audit["passives"] = []
    char.audit["passives_verification"] = VerificationState.VERIFIED
    char.audit["skills"] = []
    char.audit["skills_verification"] = VerificationState.VERIFIED

    target_build = real_builds["lvl 1-14"]

    brain_input = BuildBrainInput(
        character_state=char,
        observation_coverage=PlayerObservationCoverage(
            passives=ObservationCoverage.PARTIAL,
            skills=ObservationCoverage.PARTIAL,
        ),
    )

    result = compute_build_delta(brain_input, target_build)

    for p in result.passives:
        assert p.status != DeltaStatus.MISSING
        if p.status == DeltaStatus.UNKNOWN:
            assert p.reason in (DeltaReason.PARTIAL_PLAYER_OBSERVATION, DeltaReason.INELIGIBLE_LEVEL)

    for s in result.skills:
        assert s.status != DeltaStatus.MISSING
        if s.status == DeltaStatus.UNKNOWN:
            assert s.reason in (DeltaReason.PARTIAL_PLAYER_OBSERVATION, DeltaReason.INELIGIBLE_LEVEL)


def test_golden_stale_observation_produces_unknown_with_stale_reason(real_builds) -> None:
    """Stale player observations evaluate to UNKNOWN with reason STALE_PLAYER_STATE, never MISSING."""
    char = CharacterState.create_initial("stale_hero", "StaleHero")
    char = char.model_copy(update={"level": char.level.with_update(20, "TEST", VerificationState.STALE)})
    char.audit["passives"] = []
    char.audit["passives_verification"] = VerificationState.STALE
    char.audit["passives_is_stale"] = True
    char.audit["skills"] = []
    char.audit["skills_verification"] = VerificationState.STALE
    char.audit["skills_is_stale"] = True

    target_build = real_builds["lvl 15-32"]

    brain_input = BuildBrainInput(
        character_state=char,
        observation_coverage=PlayerObservationCoverage(
            passives=ObservationCoverage.COMPLETE,
            skills=ObservationCoverage.COMPLETE,
        ),
    )

    result = compute_build_delta(brain_input, target_build)

    for p in result.passives:
        assert p.status != DeltaStatus.MISSING
        if p.status == DeltaStatus.UNKNOWN:
            assert p.reason in (DeltaReason.STALE_PLAYER_STATE, DeltaReason.INELIGIBLE_LEVEL)

    for s in result.skills:
        assert s.status != DeltaStatus.MISSING
        if s.status == DeltaStatus.UNKNOWN:
            assert s.reason in (DeltaReason.STALE_PLAYER_STATE, DeltaReason.INELIGIBLE_LEVEL)
