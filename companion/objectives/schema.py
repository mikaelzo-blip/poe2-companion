"""Domain schemas and models for M4 Objective Engine."""

from __future__ import annotations

from enum import IntEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ObjectivePriority(IntEnum):
    """Strict 8-tier categorical priority rank for player objectives.

    Numerical values define precedence: lower numerical value = higher priority.
    No decimal scoring or continuous priority metrics allowed.
    """
    CRITICAL_MECHANIC_BREAK = 1
    HARD_BLOCKER = 2
    SURVIVAL_RISK = 3
    TRANSITION_REQUIREMENT = 4
    CURRENT_PROGRESSION = 5
    STRONG_UPGRADE = 6
    OPTIMIZATION = 7
    FUTURE_PREPARATION = 8


class EvidenceTrustworthiness(IntEnum):
    """Trustworthiness tier for secondary tie-breaking.

    Precedence: VERIFIED > SINGLE_SOURCE > STALE_OR_UNKNOWN.
    """
    VERIFIED = 1
    SINGLE_SOURCE = 2
    STALE_OR_UNKNOWN = 3


class ObjectiveHorizon(IntEnum):
    """Applicability horizon for secondary tie-breaking.

    Precedence: CURRENT > FUTURE.
    """
    CURRENT = 1
    FUTURE = 2


class CostOfIgnoring(IntEnum):
    """Impact of ignoring objective for secondary tie-breaking.

    Precedence: HIGH > LOW.
    """
    HIGH = 1
    LOW = 2


class ObjectiveCandidate(BaseModel):
    """Deterministic, immutable objective candidate emitted by generator."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    id: str
    priority: ObjectivePriority
    title: str
    action: str
    rationale: str
    source: str
    evidence_trust: EvidenceTrustworthiness = EvidenceTrustworthiness.VERIFIED
    horizon: ObjectiveHorizon = ObjectiveHorizon.CURRENT
    cost_of_ignoring: CostOfIgnoring = CostOfIgnoring.HIGH
    is_corrective: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObjectiveEvaluationResult(BaseModel):
    """Top-level structured result of an objective evaluation pass."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    character_id: str
    character_level: int | None = None
    primary_objective: ObjectiveCandidate | None = None
    all_objectives: list[ObjectiveCandidate] = Field(default_factory=list)
    status: str = "ACTIONABLE"
