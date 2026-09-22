"""Story quest progression tracking (DECOMMISSIONED per Blueprint Section 62).

Story route planning and permanent quest reward guidance are explicitly deferred
by Blueprint Section 62. This module returns structured deferred feature notices.
"""

from __future__ import annotations

from typing import Any, Iterable
from companion.intelligence.schema import (
    AdvisoryCategory,
    AdvisoryItem,
    AdvisorySeverity,
    ProvenanceCategory,
    StoryQuest,
)


def get_story_quests(completed_quest_ids: Iterable[str] | None = None) -> list[StoryQuest]:
    """Return empty list of story quests as feature is deferred."""
    return []


def get_story_deferred_notice() -> dict[str, Any]:
    """Return explicit deferred notice for story quest guidance."""
    return {
        "status": "DEFERRED_BY_BLUEPRINT",
        "feature": "story_progression",
        "blueprint_section": "62",
        "message": (
            "Story route planning and permanent quest reward databases are deferred features "
            "per Blueprint Section 62. In-game campaign tracker is the authoritative source."
        ),
    }


def evaluate_story_progression(
    current_act: int,
    completed_quest_ids: Iterable[str] | None = None,
) -> list[AdvisoryItem]:
    """Return non-authoritative deferred advisory per Blueprint Section 62."""
    return [
        AdvisoryItem(
            category=AdvisoryCategory.STORY,
            severity=AdvisorySeverity.INFO,
            title="Story Route Guidance Deferred",
            description=(
                "Story route planning and permanent quest reward guidance are deferred "
                "features per Blueprint Section 62."
            ),
            recommendation="Refer to the official in-game quest log for story objectives.",
            code="STORY_FEATURE_DEFERRED",
            is_inference=False,
            provenance=ProvenanceCategory.DEFERRED_BY_BLUEPRINT,
            context={"blueprint_section": "62", "deferred": True},
        )
    ]
