"""Unit tests for M4 Objective Engine ranking, tie-breaking, and template formatting."""

from __future__ import annotations

import pytest

from companion.objectives.engine import evaluate_objectives, rank_and_deduplicate_objectives
from companion.objectives.formatter import format_objective, format_objective_list
from companion.objectives.schema import (
    CostOfIgnoring,
    EvidenceTrustworthiness,
    ObjectiveCandidate,
    ObjectiveHorizon,
    ObjectivePriority,
)


def _cand(
    id: str,
    priority: ObjectivePriority,
    evidence_trust: EvidenceTrustworthiness = EvidenceTrustworthiness.VERIFIED,
    horizon: ObjectiveHorizon = ObjectiveHorizon.CURRENT,
    cost: CostOfIgnoring = CostOfIgnoring.HIGH,
) -> ObjectiveCandidate:
    return ObjectiveCandidate(
        id=id,
        priority=priority,
        title=f"Title for {id}",
        action=f"Action for {id}",
        rationale=f"Rationale for {id}",
        source="Test Source",
        evidence_trust=evidence_trust,
        horizon=horizon,
        cost_of_ignoring=cost,
    )


def test_ranking_primary_category_precedence():
    """Verify primary 8-tier category precedence."""
    cands = [
        _cand("future", ObjectivePriority.FUTURE_PREPARATION),
        _cand("critical", ObjectivePriority.CRITICAL_MECHANIC_BREAK),
        _cand("blocker", ObjectivePriority.HARD_BLOCKER),
        _cand("upgrade", ObjectivePriority.STRONG_UPGRADE),
        _cand("prog", ObjectivePriority.CURRENT_PROGRESSION),
    ]
    ranked = rank_and_deduplicate_objectives(cands)
    expected_ids = ["critical", "blocker", "prog", "upgrade", "future"]
    assert [c.id for c in ranked] == expected_ids


def test_ranking_tie_breaking_order():
    """Verify tie-breaking within same category:
    1. VERIFIED > SINGLE_SOURCE > STALE_OR_UNKNOWN
    2. CURRENT > FUTURE
    3. HIGH_COST > LOW_COST
    4. Deterministic stable ID.
    """
    cands = [
        _cand("c1", ObjectivePriority.CURRENT_PROGRESSION, EvidenceTrustworthiness.STALE_OR_UNKNOWN),
        _cand("c2", ObjectivePriority.CURRENT_PROGRESSION, EvidenceTrustworthiness.VERIFIED, horizon=ObjectiveHorizon.FUTURE),
        _cand("c3", ObjectivePriority.CURRENT_PROGRESSION, EvidenceTrustworthiness.VERIFIED, horizon=ObjectiveHorizon.CURRENT, cost=CostOfIgnoring.LOW),
        _cand("c4", ObjectivePriority.CURRENT_PROGRESSION, EvidenceTrustworthiness.VERIFIED, horizon=ObjectiveHorizon.CURRENT, cost=CostOfIgnoring.HIGH),
    ]
    ranked = rank_and_deduplicate_objectives(cands)
    # c4 should be first (VERIFIED, CURRENT, HIGH)
    # c3 second (VERIFIED, CURRENT, LOW)
    # c2 third (VERIFIED, FUTURE)
    # c1 fourth (STALE_OR_UNKNOWN)
    assert [c.id for c in ranked] == ["c4", "c3", "c2", "c1"]


def test_ranking_deduplication_preserves_highest_priority():
    """Deduplication by ID keeps the higher priority / earlier sorted candidate."""
    cands = [
        _cand("dup_item", ObjectivePriority.STRONG_UPGRADE),
        _cand("dup_item", ObjectivePriority.CRITICAL_MECHANIC_BREAK),
    ]
    ranked = rank_and_deduplicate_objectives(cands)
    assert len(ranked) == 1
    assert ranked[0].priority == ObjectivePriority.CRITICAL_MECHANIC_BREAK


def test_determinism_identical_inputs():
    """Identical input states produce byte-identical sorted candidate outputs."""
    cands = [
        _cand("b", ObjectivePriority.CURRENT_PROGRESSION),
        _cand("a", ObjectivePriority.CURRENT_PROGRESSION),
        _cand("z", ObjectivePriority.HARD_BLOCKER),
    ]
    res1 = rank_and_deduplicate_objectives(cands)
    res2 = rank_and_deduplicate_objectives(list(reversed(cands)))
    assert [c.id for c in res1] == [c.id for c in res2]
    assert [c.id for c in res1] == ["z", "a", "b"]


def test_empty_fallback_returns_no_actionable_objective():
    """Empty candidate list produces structured NO_ACTIONABLE_OBJECTIVE."""
    res = evaluate_objectives(
        character_id="char_clean",
        character_level=20,
        raw_candidates=[],
    )
    assert res.status == "NO_ACTIONABLE_OBJECTIVE"
    assert res.primary_objective is None
    assert res.all_objectives == []


def test_template_formatter_four_part_block():
    """Deterministic template formatter renders exact 4 parts: [PRIORITY], DO NOW, WHY, SOURCE."""
    cand = _cand("obj1", ObjectivePriority.HARD_BLOCKER)
    formatted = format_objective(cand)
    assert "[HARD_BLOCKER]" in formatted
    assert "DO NOW: Action for obj1" in formatted
    assert "WHY: Rationale for obj1" in formatted
    assert "SOURCE: Test Source" in formatted


def test_template_formatter_no_actionable():
    """Formatter renders clear message when no actionable objective exists."""
    formatted = format_objective(None)
    assert "NO_ACTIONABLE_OBJECTIVE" in formatted
    assert "Character build is synchronized" in formatted
