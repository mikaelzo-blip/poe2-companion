"""Invariant property tests for M4 Objective Engine."""

from __future__ import annotations

import pytest

from companion.objectives.engine import rank_and_deduplicate_objectives
from companion.objectives.runner import run_objective_pipeline
from companion.objectives.schema import (
    CostOfIgnoring,
    EvidenceTrustworthiness,
    ObjectiveCandidate,
    ObjectiveHorizon,
    ObjectivePriority,
)
from companion.state.schema import CharacterState


def test_invariant_ranking_monotonicity() -> None:
    """The evaluated objective list must have non-decreasing priority values (1 = highest)."""
    char = CharacterState.create_initial("hero_inv_1", "InvHero1")
    res = run_objective_pipeline(char, builds_dir="data/source/builds")
    assert len(res.all_objectives) > 0

    for i in range(len(res.all_objectives) - 1):
        curr = res.all_objectives[i]
        nxt = res.all_objectives[i + 1]
        assert curr.priority.value <= nxt.priority.value


def test_invariant_id_uniqueness() -> None:
    """No duplicate objective IDs may exist in all_objectives."""
    char = CharacterState.create_initial("hero_inv_2", "InvHero2")
    res = run_objective_pipeline(char, builds_dir="data/source/builds")

    seen = set()
    for obj in res.all_objectives:
        assert obj.id not in seen
        seen.add(obj.id)


def test_invariant_evaluation_determinism() -> None:
    """Repeated evaluation of the exact same state produces identical objective ordering and attributes."""
    char = CharacterState.create_initial("hero_inv_3", "InvHero3")
    res1 = run_objective_pipeline(char, builds_dir="data/source/builds")
    res2 = run_objective_pipeline(char, builds_dir="data/source/builds")

    assert res1.status == res2.status
    assert len(res1.all_objectives) == len(res2.all_objectives)
    for o1, o2 in zip(res1.all_objectives, res2.all_objectives):
        assert o1.id == o2.id
        assert o1.priority == o2.priority
        assert o1.action == o2.action
        assert o1.rationale == o2.rationale
        assert o1.source == o2.source


def test_invariant_uncertainty_safety() -> None:
    """Uncertain or unobserved data produces audit requests (is_corrective=False) with STALE_OR_UNKNOWN evidence."""
    char = CharacterState.create_initial("hero_inv_4", "InvHero4")
    res = run_objective_pipeline(char, builds_dir="data/source/builds")

    # In a fresh character with UNKNOWN coverage, all passive/gear candidates should be audit requests
    audit_objs = [o for o in res.all_objectives if o.evidence_trust == EvidenceTrustworthiness.STALE_OR_UNKNOWN]
    assert len(audit_objs) > 0
    for obj in audit_objs:
        assert obj.is_corrective is False
        assert obj.title.startswith("Audit")
