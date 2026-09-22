"""Unit tests for Milestone 9 story and economy deferral compliance."""

import pytest
from companion.intelligence.economy import (
    evaluate_economy_priorities,
    get_economy_deferred_notice,
)
from companion.intelligence.schema import (
    AdvisoryCategory,
    AdvisorySeverity,
    ProvenanceCategory,
)
from companion.intelligence.story import (
    evaluate_story_progression,
    get_story_deferred_notice,
    get_story_quests,
)


def test_story_feature_deferred_by_blueprint() -> None:
    """Story route guidance returns explicit deferred notice per Blueprint Section 62."""
    advisories = evaluate_story_progression(current_act=3, completed_quest_ids={"act1_caravan"})
    assert len(advisories) == 1
    adv = advisories[0]
    assert adv.code == "STORY_FEATURE_DEFERRED"
    assert adv.category == AdvisoryCategory.STORY
    assert adv.severity == AdvisorySeverity.INFO
    assert adv.provenance == ProvenanceCategory.DEFERRED_BY_BLUEPRINT
    assert "deferred" in adv.description.lower()

    quests = get_story_quests()
    assert quests == []

    notice = get_story_deferred_notice()
    assert notice["status"] == "DEFERRED_BY_BLUEPRINT"
    assert "62" in notice["blueprint_section"]


def test_economy_feature_deferred_by_blueprint() -> None:
    """Economy ROI prioritization returns empty list and explicit deferred notice."""
    priorities = evaluate_economy_priorities(
        character_level=55,
        current_resists_capped=False,
        weapon_dps_lagging=True,
    )
    assert priorities == []

    notice = get_economy_deferred_notice()
    assert notice["status"] == "DEFERRED_BY_BLUEPRINT"
    assert "62" in notice["blueprint_section"]
