"""Deterministic objective ranking, tie-breaking, and evaluation engine."""

from __future__ import annotations

from companion.objectives.schema import (
    ObjectiveCandidate,
    ObjectiveEvaluationResult,
)


def rank_and_deduplicate_objectives(
    candidates: list[ObjectiveCandidate],
) -> list[ObjectiveCandidate]:
    """Sort and deduplicate objective candidates deterministically.

    Sorting hierarchy:
    1. Priority category (1 to 8: CRITICAL_MECHANIC_BREAK down to FUTURE_PREPARATION)
    2. Evidence trustworthiness (1 to 3: VERIFIED > SINGLE_SOURCE > STALE_OR_UNKNOWN)
    3. Horizon (1 to 2: CURRENT > FUTURE)
    4. Cost of ignoring (1 to 2: HIGH > LOW)
    5. Stable candidate ID (lexicographical total order)

    Deduplication:
    Retains only the first (highest-ranking) candidate per unique candidate ID.
    """
    sorted_candidates = sorted(
        candidates,
        key=lambda c: (
            c.priority.value,
            c.evidence_trust.value,
            c.horizon.value,
            c.cost_of_ignoring.value,
            c.id,
        ),
    )

    seen_ids: set[str] = set()
    deduped: list[ObjectiveCandidate] = []
    for c in sorted_candidates:
        if c.id not in seen_ids:
            seen_ids.add(c.id)
            deduped.append(c)

    return deduped


def evaluate_objectives(
    character_id: str,
    character_level: int | None,
    raw_candidates: list[ObjectiveCandidate],
) -> ObjectiveEvaluationResult:
    """Evaluate raw objective candidates into a structured ObjectiveEvaluationResult.

    Selects the single top-priority primary objective and provides the full deterministic list.
    Returns NO_ACTIONABLE_OBJECTIVE status when no candidates exist.
    """
    ranked = rank_and_deduplicate_objectives(raw_candidates)

    if not ranked:
        return ObjectiveEvaluationResult(
            character_id=character_id,
            character_level=character_level,
            primary_objective=None,
            all_objectives=[],
            status="NO_ACTIONABLE_OBJECTIVE",
        )

    return ObjectiveEvaluationResult(
        character_id=character_id,
        character_level=character_level,
        primary_objective=ranked[0],
        all_objectives=ranked,
        status="ACTIONABLE",
    )
