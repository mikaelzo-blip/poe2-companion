"""Deterministic level interval eligibility evaluation for PoE2 build elements."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict

from companion.sources.interval import IntervalKind, LevelInterval
from companion.build.validation import validate_character_level


class EligibilityState(str, Enum):
    """Semantic level eligibility status for build elements."""
    ACTIVE = "ACTIVE"
    FUTURE = "FUTURE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class EligibilityEvaluation(BaseModel):
    """Result of evaluating a level interval against a character level."""
    model_config = ConfigDict(frozen=True)

    state: EligibilityState
    unresolved_semantics: bool = False


def evaluate_eligibility(
    interval: LevelInterval | None,
    character_level: int | None,
) -> EligibilityEvaluation:
    """Evaluate a level interval against an observed character level.

    Boundary rules:
    - Strictly validates character_level via validate_character_level.
    - Unrestricted interval (or None/omitted) evaluates to ACTIVE across all levels, including None.
    - Bounded range [min, max]:
        - If character_level is None: evaluates to UNKNOWN.
        - If character_level < min: evaluates to FUTURE.
        - If min <= character_level <= max: evaluates to ACTIVE.
        - If character_level > max: evaluates to EXPIRED.
    - Unresolved single uint: evaluates to UNKNOWN with unresolved_semantics=True.
    """
    valid_level = validate_character_level(character_level)

    if interval is None or interval.kind == IntervalKind.UNRESTRICTED:
        return EligibilityEvaluation(state=EligibilityState.ACTIVE)

    if interval.kind == IntervalKind.RANGE:
        if valid_level is None:
            return EligibilityEvaluation(state=EligibilityState.UNKNOWN)
        assert interval.min_level is not None and interval.max_level is not None
        if valid_level < interval.min_level:
            return EligibilityEvaluation(state=EligibilityState.FUTURE)
        if valid_level <= interval.max_level:
            return EligibilityEvaluation(state=EligibilityState.ACTIVE)
        return EligibilityEvaluation(state=EligibilityState.EXPIRED)

    if interval.kind == IntervalKind.UNRESOLVED_SINGLE_UINT:
        return EligibilityEvaluation(
            state=EligibilityState.UNKNOWN,
            unresolved_semantics=True,
        )

    return EligibilityEvaluation(state=EligibilityState.UNKNOWN)
