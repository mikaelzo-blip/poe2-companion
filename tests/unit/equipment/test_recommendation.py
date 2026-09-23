"""Unit tests for recommendation report formatting and factual delineation."""

import pytest
from companion.equipment.schema import SlotType
from companion.equipment.parser import parse_item_text
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.partial_projection import project_candidate_on_loadout
from companion.equipment.requirements import RequirementCascadeResult
from companion.equipment.rules import BuildBreakerEvaluation, BuildBreakerCertainty
from companion.equipment.precedence import Verdict
from companion.equipment.recommendation import (
    EquipmentRecommendation,
    format_recommendation_report,
)

BOOTS_TEXT = """Item Class: Boots
Rarity: Rare
Loath Trail
Furtive Boots
--------
Requirements:
Level: 45
--------
+66 to maximum Life
+28% to Lightning Resistance
+10% increased Movement Speed
"""


def test_format_recommendation_delineates_known_and_unknown():
    loadout = EquippedLoadout.create_draft(character_id="char_fmt")
    cand = parse_item_text(BOOTS_TEXT, target_slot=SlotType.BOOTS)
    baseline = CharacterStatBaseline.create_empty(character_id="char_fmt", anchored_loadout_revision=1)
    proj = project_candidate_on_loadout(loadout, cand, SlotType.BOOTS, baseline=baseline)

    rec = EquipmentRecommendation(
        character_id="char_fmt",
        slot=SlotType.BOOTS,
        candidate=cand,
        displaced_items=[],
        projection=proj,
        safety_eval=BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE),
        cascade_result=RequirementCascadeResult(is_satisfied=True),
        verdict=Verdict.EQUIP_NOW,
        verdict_reason="Clean upgrade for empty slot.",
        flags=["EMPTY_SLOT_UPGRADE"],
    )

    report = format_recommendation_report(rec)
    assert "EQUIP_NOW" in report
    assert "Loath Trail" in report
    assert "KNOWN DELTAS" in report
    assert "PROJECTED ABSOLUTE" in report
    assert "UNKNOWN" in report
