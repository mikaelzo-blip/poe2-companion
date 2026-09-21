"""Tests for M4 Objective Engine domain schemas and models."""

from __future__ import annotations

import json
import pytest
from pydantic import ValidationError

from companion.objectives.schema import (
    CostOfIgnoring,
    EvidenceTrustworthiness,
    ObjectiveCandidate,
    ObjectiveEvaluationResult,
    ObjectiveHorizon,
    ObjectivePriority,
)


def test_objective_priority_eight_tiers_exact_precedence():
    """Verify exact 8 tiers in strict ascending order of priority value (1 = most critical)."""
    assert ObjectivePriority.CRITICAL_MECHANIC_BREAK == 1
    assert ObjectivePriority.HARD_BLOCKER == 2
    assert ObjectivePriority.SURVIVAL_RISK == 3
    assert ObjectivePriority.TRANSITION_REQUIREMENT == 4
    assert ObjectivePriority.CURRENT_PROGRESSION == 5
    assert ObjectivePriority.STRONG_UPGRADE == 6
    assert ObjectivePriority.OPTIMIZATION == 7
    assert ObjectivePriority.FUTURE_PREPARATION == 8
    assert len(ObjectivePriority) == 8


def test_secondary_sorting_enums():
    """Verify secondary tie-breaking enums."""
    assert EvidenceTrustworthiness.VERIFIED == 1
    assert EvidenceTrustworthiness.SINGLE_SOURCE == 2
    assert EvidenceTrustworthiness.STALE_OR_UNKNOWN == 3

    assert ObjectiveHorizon.CURRENT == 1
    assert ObjectiveHorizon.FUTURE == 2

    assert CostOfIgnoring.HIGH == 1
    assert CostOfIgnoring.LOW == 2


def test_objective_candidate_creation_and_immutability():
    """Verify creation and immutability of ObjectiveCandidate."""
    cand = ObjectiveCandidate(
        id="test:obj1",
        priority=ObjectivePriority.CRITICAL_MECHANIC_BREAK,
        title="Fix Weapon Set",
        action="Verify weapon slots",
        rationale="Weapon configuration violates transition rule",
        source="Fubgun rule",
        evidence_trust=EvidenceTrustworthiness.VERIFIED,
        horizon=ObjectiveHorizon.CURRENT,
        cost_of_ignoring=CostOfIgnoring.HIGH,
        is_corrective=True,
    )
    assert cand.id == "test:obj1"
    assert cand.priority == ObjectivePriority.CRITICAL_MECHANIC_BREAK
    assert cand.is_corrective is True

    # Immutable / frozen
    with pytest.raises(ValidationError):
        cand.id = "new_id"  # type: ignore


def test_objective_evaluation_result_serialization_and_empty_state():
    """Verify round-trip JSON serialization of ObjectiveEvaluationResult."""
    result = ObjectiveEvaluationResult(
        character_id="char_01",
        character_level=52,
        primary_objective=None,
        all_objectives=[],
        status="NO_ACTIONABLE_OBJECTIVE",
    )
    dumped = result.model_dump_json()
    loaded = json.loads(dumped)
    assert loaded["character_id"] == "char_01"
    assert loaded["status"] == "NO_ACTIONABLE_OBJECTIVE"
    assert loaded["primary_objective"] is None
    assert loaded["all_objectives"] == []

    parsed = ObjectiveEvaluationResult.model_validate_json(dumped)
    assert parsed.character_id == "char_01"
    assert parsed.status == "NO_ACTIONABLE_OBJECTIVE"
