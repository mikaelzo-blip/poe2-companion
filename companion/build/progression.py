"""Deterministic progression phase resolution and 69-84 fallback specification."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from pydantic import BaseModel, ConfigDict

from companion.build.validation import validate_character_level

if TYPE_CHECKING:
    from companion.state.schema import CharacterState


class ProgressionPhase(str, Enum):
    """Character progression phases mapping to target build snapshots."""
    LEVELING_1_14 = "LEVELING_1_14"
    LEVELING_15_32 = "LEVELING_15_32"
    LEVELING_33_51 = "LEVELING_33_51"
    POST_52_53_68 = "POST_52_53_68"
    LEVELING_69_84_FALLBACK = "LEVELING_69_84_FALLBACK"
    HIGH_END = "HIGH_END"
    UNKNOWN = "UNKNOWN"


class ProgressionResolution(BaseModel):
    """Structured result of resolving progression phase from character level."""
    model_config = ConfigDict(frozen=True)

    phase: ProgressionPhase
    target_snapshot_name: str | None = None
    provenance: str | None = None


def resolve_progression_phase(
    level_or_state: int | None | CharacterState,
) -> ProgressionResolution:
    """Deterministically map character level to an explicit progression phase.

    Boundaries:
    - 1 to 14 -> LEVELING_1_14 (snapshot 'lvl 1-14')
    - 15 to 32 -> LEVELING_15_32 (snapshot 'lvl 15-32')
    - 33 to 51 -> LEVELING_33_51 (snapshot 'lvl 33-51')
    - 52 to 68 -> POST_52_53_68 (snapshot 'lvl 53-68')
    - 69 to 84 -> LEVELING_69_84_FALLBACK (snapshot 'lvl 53-68', provenance 'COMPANION_FALLBACK_SOURCE_GAP')
    - 85 to 100 -> HIGH_END (requires high-end variant resolution)
    - None / unobserved -> UNKNOWN

    Defends strictly against invalid levels (<= 0 or > 100) via validate_character_level.
    Strictly isolated from M3 transition state machine flags (PREPARING, BLOCKED, etc.).
    """
    if hasattr(level_or_state, "level"):
        raw_level = level_or_state.level.value
    else:
        raw_level = level_or_state

    valid_level = validate_character_level(raw_level)

    if valid_level is None:
        return ProgressionResolution(
            phase=ProgressionPhase.UNKNOWN,
            target_snapshot_name=None,
            provenance="UNOBSERVED_CHARACTER_LEVEL",
        )

    if 1 <= valid_level <= 14:
        return ProgressionResolution(
            phase=ProgressionPhase.LEVELING_1_14,
            target_snapshot_name="lvl 1-14",
            provenance="CANONICAL_UPSTREAM_SNAPSHOT",
        )
    if 15 <= valid_level <= 32:
        return ProgressionResolution(
            phase=ProgressionPhase.LEVELING_15_32,
            target_snapshot_name="lvl 15-32",
            provenance="CANONICAL_UPSTREAM_SNAPSHOT",
        )
    if 33 <= valid_level <= 51:
        return ProgressionResolution(
            phase=ProgressionPhase.LEVELING_33_51,
            target_snapshot_name="lvl 33-51",
            provenance="CANONICAL_UPSTREAM_SNAPSHOT",
        )
    if 52 <= valid_level <= 68:
        return ProgressionResolution(
            phase=ProgressionPhase.POST_52_53_68,
            target_snapshot_name="lvl 53-68",
            provenance="CANONICAL_UPSTREAM_SNAPSHOT",
        )
    if 69 <= valid_level <= 84:
        return ProgressionResolution(
            phase=ProgressionPhase.LEVELING_69_84_FALLBACK,
            target_snapshot_name="lvl 53-68",
            provenance="COMPANION_FALLBACK_SOURCE_GAP",
        )
    # 85 to 100
    return ProgressionResolution(
        phase=ProgressionPhase.HIGH_END,
        target_snapshot_name=None,
        provenance="REQUIRES_HIGH_END_VARIANT",
    )
