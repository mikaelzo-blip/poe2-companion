"""Transition management package for PoE2 character progression milestones.

Implements persistent transition state evaluation, requirement readiness aggregation,
and future requirement isolation (Milestone 3).
"""

from __future__ import annotations

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

__all__ = [
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
