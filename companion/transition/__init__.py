"""Transition management package for PoE2 character progression milestones.

Implements persistent transition state evaluation, requirement readiness aggregation,
future requirement isolation, and level-52 transition state machine (Milestone 3).
"""

from __future__ import annotations

from companion.transition.evaluator import (
    InvalidTransitionError,
    can_transition,
    evaluate_level52_transition,
    trigger_transition_start,
)
from companion.transition.requirements import (
    RequirementEvaluation,
    RequirementReadiness,
    evaluate_requirements,
    evaluate_single_requirement,
    get_active_blocking_requirements,
    get_applicable_blocking_requirements,
    has_unknown_blocker,
    has_unsatisfied_blocker,
    is_transition_ready,
)
from companion.transition.state import (
    Level52TransitionRecord,
    Level52TransitionResult,
    Level52TransitionState,
)

__all__ = [
    # State & Record Models (Phase 4, Task 4.1)
    "Level52TransitionState",
    "Level52TransitionRecord",
    "Level52TransitionResult",
    # Transition Evaluator & Actions (Phase 4, Task 4.2)
    "evaluate_level52_transition",
    "trigger_transition_start",
    "can_transition",
    "InvalidTransitionError",
    # Requirement Models & Functions (Phase 3, Tasks 3.1, 3.2)
    "RequirementReadiness",
    "RequirementEvaluation",
    "evaluate_requirements",
    "evaluate_single_requirement",
    "get_active_blocking_requirements",
    "get_applicable_blocking_requirements",
    "has_unsatisfied_blocker",
    "has_unknown_blocker",
    "is_transition_ready",
]
