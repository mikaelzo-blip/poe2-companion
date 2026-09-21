"""Target build variant models and non-monotonic high-end variant resolver."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict

from companion.build.progression import ProgressionPhase


class TargetVariant(str, Enum):
    """Explicit selectable target build variants."""
    NONE = "NONE"
    LVL85 = "LVL85"
    ENDGAME = "ENDGAME"
    MAGEBLOOD = "MAGEBLOOD"
    DOT_CAP = "DOT_CAP"


class VariantResolutionStatus(str, Enum):
    """Status of high-end target variant resolution."""
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


HIGH_END_SNAPSHOT_MAP: dict[TargetVariant, str] = {
    TargetVariant.LVL85: "lvl 85",
    TargetVariant.ENDGAME: "Endgame",
    TargetVariant.MAGEBLOOD: "Mageblood",
    TargetVariant.DOT_CAP: "DoT Cap",
}


class TargetVariantResolution(BaseModel):
    """Structured result of target build variant resolution."""
    model_config = ConfigDict(frozen=True)

    variant: TargetVariant | None = None
    status: VariantResolutionStatus
    reason: str | None = None
    source: str | None = None
    target_snapshot_name: str | None = None


def resolve_target_variant(
    phase: ProgressionPhase,
    selected_target_variant: TargetVariant | None = None,
) -> TargetVariantResolution:
    """Deterministically resolve target build variant without implicit defaults.

    Rules:
    - Outside HIGH_END phase: returns variant=NONE with status=NOT_APPLICABLE.
    - Inside HIGH_END phase with selected_target_variant as None or NONE:
      returns variant=None with status=UNRESOLVED and reason='NO_EXPLICIT_HIGH_END_VARIANT'.
      NEVER defaults to LVL85.
    - Inside HIGH_END phase with explicit variant selection:
      returns variant with status=RESOLVED and maps target snapshot name.
    - Item ownership (equipped or inventory) NEVER silently resolves or mutates the variant.
    """
    if phase != ProgressionPhase.HIGH_END:
        return TargetVariantResolution(
            variant=TargetVariant.NONE,
            status=VariantResolutionStatus.NOT_APPLICABLE,
            reason="NOT_HIGH_END_PHASE",
            target_snapshot_name=None,
        )

    if selected_target_variant is None or selected_target_variant == TargetVariant.NONE:
        return TargetVariantResolution(
            variant=None,
            status=VariantResolutionStatus.UNRESOLVED,
            reason="NO_EXPLICIT_HIGH_END_VARIANT",
            target_snapshot_name=None,
        )

    snapshot_name = HIGH_END_SNAPSHOT_MAP.get(selected_target_variant)
    return TargetVariantResolution(
        variant=selected_target_variant,
        status=VariantResolutionStatus.RESOLVED,
        source="EXPLICIT_SELECTION",
        target_snapshot_name=snapshot_name,
    )
