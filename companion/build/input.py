"""Explicit input contract and subsystem observation coverage for PoE2 Build Brain."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from companion.state.schema import CharacterState
from companion.build.variants import TargetVariant


class ObservationCoverage(str, Enum):
    """Observation comprehensiveness within a specific character subsystem or slot."""
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class PlayerObservationCoverage(BaseModel):
    """Explicit observation coverage across character subsystems."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    passives: ObservationCoverage = ObservationCoverage.UNKNOWN
    skills: ObservationCoverage = ObservationCoverage.UNKNOWN
    equipment_slots: dict[str, ObservationCoverage] = Field(default_factory=dict)


class BuildBrainInput(BaseModel):
    """Explicit offline input contract for the M2 Build Brain."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    character_state: CharacterState
    observation_coverage: PlayerObservationCoverage = Field(default_factory=PlayerObservationCoverage)
    selected_target_variant: TargetVariant | None = None
