"""Unit tests for Milestone 9 story guidance and economy prioritization."""

import pytest
from companion.intelligence.economy import evaluate_economy_priorities
from companion.intelligence.schema import AdvisoryCategory, AdvisorySeverity
from companion.intelligence.story import evaluate_story_progression, get_story_quests


def test_story_progression_missed_permanent_reward() -> None:
    # Player in Act 3, but hasn't done Act 1 Spirit Shrine
    advisories = evaluate_story_progression(current_act=3, completed_quest_ids={"act1_caravan"})
    
    missed = [a for a in advisories if a.code == "STORY_MISSED_PERMANENT_REWARD"]
    assert len(missed) >= 1
    assert any("spirit" in a.description.lower() for a in missed)
    assert all(a.severity == AdvisorySeverity.WARNING for a in missed)


def test_story_quests_list() -> None:
    quests = get_story_quests(completed_quest_ids={"act1_caravan"})
    assert len(quests) >= 4
    caravan = next(q for q in quests if q.quest_id == "act1_caravan")
    assert caravan.completed is True


def test_economy_priority_resists_uncapped() -> None:
    priorities = evaluate_economy_priorities(
        character_level=55,
        current_resists_capped=False,
        weapon_dps_lagging=True,
    )
    assert len(priorities) >= 1
    # First priority must address resistances
    assert priorities[0].priority_tier == 1
    assert "resist" in priorities[0].roi_reason.lower()


def test_economy_priority_weapon_upgrade_when_capped() -> None:
    priorities = evaluate_economy_priorities(
        character_level=55,
        current_resists_capped=True,
        weapon_dps_lagging=True,
    )
    assert len(priorities) >= 1
    assert priorities[0].priority_tier == 1
    assert "weapon" in priorities[0].target_slot.lower()
