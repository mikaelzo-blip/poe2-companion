"""Story quest progression tracking: permanent passive skill books and spirit capacity shrines."""

from __future__ import annotations

from typing import Iterable
from companion.intelligence.schema import (
    AdvisoryCategory,
    AdvisoryItem,
    AdvisorySeverity,
    StoryQuest,
)

CORE_STORY_QUESTS: list[StoryQuest] = [
    StoryQuest(
        quest_id="act1_caravan",
        act=1,
        name="The Lost Caravan",
        reward_type="PASSIVE",
        reward_detail="+1 Passive Skill Point (Book of Skill)",
    ),
    StoryQuest(
        quest_id="act1_ogham_spirit",
        act=1,
        name="Ogham Spirit Shrine",
        reward_type="SPIRIT",
        reward_detail="+30 Permanent Spirit Capacity",
    ),
    StoryQuest(
        quest_id="act2_bandit_lords",
        act=2,
        name="The Bandit Lords",
        reward_type="BANDIT",
        reward_detail="Bandit perk / passives",
    ),
    StoryQuest(
        quest_id="act2_vaal_enclave_spirit",
        act=2,
        name="Vaal Enclave Shrine",
        reward_type="SPIRIT",
        reward_detail="+30 Permanent Spirit Capacity",
    ),
    StoryQuest(
        quest_id="act3_catacombs",
        act=3,
        name="Aggorat Catacombs",
        reward_type="PASSIVE",
        reward_detail="+1 Passive Skill Point (Book of Skill)",
    ),
    StoryQuest(
        quest_id="act3_tower_spirit",
        act=3,
        name="Tower of the Sun",
        reward_type="SPIRIT",
        reward_detail="+40 Permanent Spirit Capacity",
    ),
]


def get_story_quests(completed_quest_ids: Iterable[str] | None = None) -> list[StoryQuest]:
    """Retrieve full catalog of permanent reward quests with completion flags."""
    completed = set(completed_quest_ids or [])
    return [
        quest.model_copy(update={"completed": quest.quest_id in completed})
        for quest in CORE_STORY_QUESTS
    ]


def evaluate_story_progression(
    current_act: int,
    completed_quest_ids: Iterable[str] | None = None,
) -> list[AdvisoryItem]:
    """Warn player if they entered higher acts without claiming earlier permanent rewards."""
    completed = set(completed_quest_ids or [])
    advisories: list[AdvisoryItem] = []

    for quest in CORE_STORY_QUESTS:
        if current_act > quest.act and quest.quest_id not in completed:
            advisories.append(
                AdvisoryItem(
                    category=AdvisoryCategory.STORY,
                    severity=AdvisorySeverity.WARNING,
                    title=f"Unclaimed Permanent Reward: Act {quest.act}",
                    description=f"You are in Act {current_act} but have not completed '{quest.name}' in Act {quest.act} ({quest.reward_detail}).",
                    recommendation=f"Return to Act {quest.act} and complete '{quest.name}' to claim {quest.reward_detail}.",
                    code="STORY_MISSED_PERMANENT_REWARD",
                    context={
                        "quest_id": quest.quest_id,
                        "act": quest.act,
                        "reward_type": quest.reward_type,
                    },
                )
            )

    return advisories
