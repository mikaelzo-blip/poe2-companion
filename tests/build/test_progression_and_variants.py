"""Unit tests for progression phase resolution, 69-84 fallback policy, and high-end variant resolver."""

import pytest
from companion.state.schema import CharacterState
from companion.build.validation import InvalidCharacterLevelError
from companion.build.progression import (
    ProgressionPhase,
    ProgressionResolution,
    resolve_progression_phase,
)
from companion.build.input import (
    BuildBrainInput,
    ObservationCoverage,
    PlayerObservationCoverage,
)
from companion.build.variants import (
    TargetVariant,
    TargetVariantResolution,
    VariantResolutionStatus,
    resolve_target_variant,
)


def test_resolve_progression_phase_exact_boundaries() -> None:
    """Verify exact boundary progression phase transitions across levels 1 to 100."""
    # 1 -> LEVELING_1_14 (lvl 1-14)
    r1 = resolve_progression_phase(1)
    assert r1.phase == ProgressionPhase.LEVELING_1_14
    assert r1.target_snapshot_name == "lvl 1-14"

    # 14 -> LEVELING_1_14 (lvl 1-14)
    r14 = resolve_progression_phase(14)
    assert r14.phase == ProgressionPhase.LEVELING_1_14
    assert r14.target_snapshot_name == "lvl 1-14"

    # 15 -> LEVELING_15_32 (lvl 15-32)
    r15 = resolve_progression_phase(15)
    assert r15.phase == ProgressionPhase.LEVELING_15_32
    assert r15.target_snapshot_name == "lvl 15-32"

    # 32 -> LEVELING_15_32 (lvl 15-32)
    r32 = resolve_progression_phase(32)
    assert r32.phase == ProgressionPhase.LEVELING_15_32
    assert r32.target_snapshot_name == "lvl 15-32"

    # 33 -> LEVELING_33_51 (lvl 33-51)
    r33 = resolve_progression_phase(33)
    assert r33.phase == ProgressionPhase.LEVELING_33_51
    assert r33.target_snapshot_name == "lvl 33-51"

    # 51 -> LEVELING_33_51 (lvl 33-51)
    r51 = resolve_progression_phase(51)
    assert r51.phase == ProgressionPhase.LEVELING_33_51
    assert r51.target_snapshot_name == "lvl 33-51"

    # 52 -> POST_52_53_68 (lvl 53-68)
    r52 = resolve_progression_phase(52)
    assert r52.phase == ProgressionPhase.POST_52_53_68
    assert r52.target_snapshot_name == "lvl 53-68"

    # 53 -> POST_52_53_68 (lvl 53-68)
    r53 = resolve_progression_phase(53)
    assert r53.phase == ProgressionPhase.POST_52_53_68
    assert r53.target_snapshot_name == "lvl 53-68"

    # 58 -> POST_52_53_68 (lvl 53-68)
    r58 = resolve_progression_phase(58)
    assert r58.phase == ProgressionPhase.POST_52_53_68
    assert r58.target_snapshot_name == "lvl 53-68"

    # 68 -> POST_52_53_68 (lvl 53-68)
    r68 = resolve_progression_phase(68)
    assert r68.phase == ProgressionPhase.POST_52_53_68
    assert r68.target_snapshot_name == "lvl 53-68"
    assert r68.provenance != "COMPANION_FALLBACK_SOURCE_GAP"

    # 69 -> LEVELING_69_84_FALLBACK with exact lvl 53-68 snapshot and COMPANION_FALLBACK_SOURCE_GAP
    r69 = resolve_progression_phase(69)
    assert r69.phase == ProgressionPhase.LEVELING_69_84_FALLBACK
    assert r69.target_snapshot_name == "lvl 53-68"
    assert r69.provenance == "COMPANION_FALLBACK_SOURCE_GAP"

    # 84 -> LEVELING_69_84_FALLBACK with exact lvl 53-68 snapshot and COMPANION_FALLBACK_SOURCE_GAP
    r84 = resolve_progression_phase(84)
    assert r84.phase == ProgressionPhase.LEVELING_69_84_FALLBACK
    assert r84.target_snapshot_name == "lvl 53-68"
    assert r84.provenance == "COMPANION_FALLBACK_SOURCE_GAP"

    # 85 -> HIGH_END
    r85 = resolve_progression_phase(85)
    assert r85.phase == ProgressionPhase.HIGH_END

    # 100 -> HIGH_END
    r100 = resolve_progression_phase(100)
    assert r100.phase == ProgressionPhase.HIGH_END


def test_resolve_progression_phase_unknown_and_invalid() -> None:
    """Unknown level yields UNKNOWN phase; invalid levels raise InvalidCharacterLevelError."""
    r_none = resolve_progression_phase(None)
    assert r_none.phase == ProgressionPhase.UNKNOWN
    assert r_none.target_snapshot_name is None

    with pytest.raises(InvalidCharacterLevelError):
        resolve_progression_phase(0)

    with pytest.raises(InvalidCharacterLevelError):
        resolve_progression_phase(-5)

    with pytest.raises(InvalidCharacterLevelError):
        resolve_progression_phase(101)


def test_resolve_progression_phase_from_character_state() -> None:
    """Progression resolver can extract level from CharacterState."""
    char = CharacterState.create_initial(character_id="hero1", character_name="Hero")
    char_lvl52 = char.model_copy(update={"level": char.level.with_update(52, "TEST", char.level.verification_state)})
    r = resolve_progression_phase(char_lvl52)
    assert r.phase == ProgressionPhase.POST_52_53_68
    assert r.target_snapshot_name == "lvl 53-68"


def test_target_variant_resolution_outside_high_end() -> None:
    """Outside HIGH_END phase, variant resolution returns NONE with status NOT_APPLICABLE."""
    for phase in [
        ProgressionPhase.LEVELING_1_14,
        ProgressionPhase.LEVELING_15_32,
        ProgressionPhase.LEVELING_33_51,
        ProgressionPhase.POST_52_53_68,
        ProgressionPhase.LEVELING_69_84_FALLBACK,
        ProgressionPhase.UNKNOWN,
    ]:
        res = resolve_target_variant(phase, selected_target_variant=TargetVariant.LVL85)
        assert res.variant == TargetVariant.NONE
        assert res.status == VariantResolutionStatus.NOT_APPLICABLE


def test_target_variant_high_end_unselected_returns_unresolved_not_lvl85() -> None:
    """In HIGH_END phase, when selected_target_variant is None, return UNRESOLVED (NEVER default to LVL85)."""
    res = resolve_target_variant(ProgressionPhase.HIGH_END, selected_target_variant=None)
    assert res.variant is None
    assert res.status == VariantResolutionStatus.UNRESOLVED
    assert res.reason == "NO_EXPLICIT_HIGH_END_VARIANT"


def test_target_variant_high_end_explicit_variants() -> None:
    """In HIGH_END phase, explicitly selecting each variant resolves correctly."""
    v_lvl85 = resolve_target_variant(ProgressionPhase.HIGH_END, TargetVariant.LVL85)
    assert v_lvl85.variant == TargetVariant.LVL85
    assert v_lvl85.status == VariantResolutionStatus.RESOLVED
    assert v_lvl85.target_snapshot_name == "lvl 85"

    v_endgame = resolve_target_variant(ProgressionPhase.HIGH_END, TargetVariant.ENDGAME)
    assert v_endgame.variant == TargetVariant.ENDGAME
    assert v_endgame.status == VariantResolutionStatus.RESOLVED
    assert v_endgame.target_snapshot_name == "Endgame"

    v_mb = resolve_target_variant(ProgressionPhase.HIGH_END, TargetVariant.MAGEBLOOD)
    assert v_mb.variant == TargetVariant.MAGEBLOOD
    assert v_mb.status == VariantResolutionStatus.RESOLVED
    assert v_mb.target_snapshot_name == "Mageblood"

    v_dot = resolve_target_variant(ProgressionPhase.HIGH_END, TargetVariant.DOT_CAP)
    assert v_dot.variant == TargetVariant.DOT_CAP
    assert v_dot.status == VariantResolutionStatus.RESOLVED
    assert v_dot.target_snapshot_name == "DoT Cap"


def test_variant_resolution_never_inferred_from_items() -> None:
    """Item possession (e.g. Mageblood) must never mutate or resolve variant."""
    # Regardless of what items exist on character, resolve_target_variant adheres strictly to input
    res_none = resolve_target_variant(ProgressionPhase.HIGH_END, selected_target_variant=None)
    assert res_none.status == VariantResolutionStatus.UNRESOLVED
    assert res_none.variant is None

    res_lvl85 = resolve_target_variant(ProgressionPhase.HIGH_END, selected_target_variant=TargetVariant.LVL85)
    assert res_lvl85.variant == TargetVariant.LVL85
    assert res_lvl85.status == VariantResolutionStatus.RESOLVED


def test_build_brain_input_contract() -> None:
    """BuildBrainInput wraps character_state, observation_coverage, and selected_target_variant."""
    char = CharacterState.create_initial(character_id="hero1", character_name="Hero")
    coverage = PlayerObservationCoverage(
        passives=ObservationCoverage.COMPLETE,
        skills=ObservationCoverage.PARTIAL,
        equipment_slots={"Helm": ObservationCoverage.COMPLETE},
    )
    brain_input = BuildBrainInput(
        character_state=char,
        observation_coverage=coverage,
        selected_target_variant=TargetVariant.MAGEBLOOD,
    )
    assert brain_input.character_state.character_id == "hero1"
    assert brain_input.observation_coverage.passives == ObservationCoverage.COMPLETE
    assert brain_input.observation_coverage.equipment_slots["Helm"] == ObservationCoverage.COMPLETE
    assert brain_input.selected_target_variant == TargetVariant.MAGEBLOOD
