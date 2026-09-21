"""Persistent transition states, record schemas, and evaluation result models.

Implements Milestone 3 Phase 4 (Task 4.1):
- Canonical seven persistent transition states: Level52TransitionState.
- Persistent record model: Level52TransitionRecord.
- Root transition evaluation result model: Level52TransitionResult.
- Deterministically derived current-condition status properties:
  - transition_pending (character_level > 52 and state != COMPLETE)
  - missed_transition (character_level > 52 and state != COMPLETE and has_verified_preswap_evidence)
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from pydantic import BaseModel, ConfigDict, Field

from companion.transition.requirements import RequirementEvaluation, RequirementReadiness

if TYPE_CHECKING:
    pass


class Level52TransitionState(str, Enum):
    """Canonical seven persistent progression states for Level-52 weapon swap milestone."""
    NOT_RELEVANT = "NOT_RELEVANT"
    PREPARING = "PREPARING"
    VERIFYING = "VERIFYING"
    BLOCKED = "BLOCKED"
    READY = "READY"
    TRANSITIONING = "TRANSITIONING"
    COMPLETE = "COMPLETE"


class Level52TransitionRecord(BaseModel):
    """Persistent storage record for Level-52 milestone transition in CharacterState."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    state: Level52TransitionState = Level52TransitionState.NOT_RELEVANT
    requirements: dict[str, RequirementReadiness] = Field(default_factory=dict)
    last_evaluated_at: str | None = None
    verified_at: str | None = None
    notes: str | None = None


class Level52TransitionResult(BaseModel):
    """Root evaluation result for Level-52 progression milestone transition.

    Enforces that status flags (transition_pending, missed_transition) are deterministically
    derived current conditions rather than independently mutable persisted facts that could drift.
    """
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    state: Level52TransitionState
    character_level: int
    requirements: list[RequirementEvaluation] = Field(default_factory=list)
    blocking_requirements: list[RequirementEvaluation] = Field(default_factory=list)
    completion_markers: list[RequirementEvaluation] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    has_verified_preswap_evidence: bool = False
    evaluated_at: str | None = None
    notes: str | None = None

    @property
    def transition_pending(self) -> bool:
        """True if character_level > 52 and state != COMPLETE."""
        return (
            self.character_level is not None
            and self.character_level > 52
            and self.state != Level52TransitionState.COMPLETE
        )

    @property
    def missed_transition(self) -> bool:
        """True if character_level > 52, state != COMPLETE, and verified pre-swap evidence active.

        Strictly evaluates to False once state is COMPLETE.
        """
        return (
            self.character_level is not None
            and self.character_level > 52
            and self.state != Level52TransitionState.COMPLETE
            and self.has_verified_preswap_evidence
        )

    def to_record(self) -> Level52TransitionRecord:
        """Convert evaluation result into persistent Level52TransitionRecord."""
        return Level52TransitionRecord(
            state=self.state,
            requirements={req.rule_id: req.readiness for req in self.requirements},
            last_evaluated_at=self.evaluated_at,
            verified_at=self.evaluated_at if self.state == Level52TransitionState.COMPLETE else None,
            notes=self.notes,
        )
