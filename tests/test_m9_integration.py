"""End-to-end integration test for Milestone 9 expanded build intelligence pipeline."""

from pathlib import Path
import pytest

from companion.gear.schema import EquippedItem, GearAuditState, ItemMod, ItemRarity, ItemSlot
from companion.intelligence import (
    AdvisoryCategory,
    AdvisorySeverity,
    evaluate_economy_priorities,
    evaluate_gear_rules,
    evaluate_story_progression,
    evaluate_survival_rules,
    evaluate_troubleshooting_rules,
    get_story_quests,
)
from companion.state.provenance import VerificationState
from companion.vision.schema import CharacterPanelStats


def test_m9_expanded_intelligence_end_to_end_pipeline() -> None:
    # 1. Survival rules evaluation with real observed panel stats
    panel_stats = CharacterPanelStats(
        life=1900,
        mana=600,
        spirit=120,
        fire_res=75,
        cold_res=50,  # Uncapped in maps
        lightning_res=75,
        chaos_res=-40,  # Dangerous
        armour=2200,
        evasion=1100,
    )
    survival_adv = evaluate_survival_rules(panel_stats=panel_stats, character_level=68, current_act=7)
    assert any(a.code == "RES_UNCAPPED_COLD" and a.severity == AdvisorySeverity.CRITICAL for a in survival_adv)
    assert any(a.code == "CHAOS_RES_LOW" for a in survival_adv)

    # 2. Gear rules evaluation with audited gear state
    helm = EquippedItem(
        slot=ItemSlot.HELMET,
        name="Crown of Thorns",
        base_type="Iron Helmet",
        rarity=ItemRarity.RARE,
        item_level=30,  # 38 levels behind level 68
        explicit_mods=[
            ItemMod(raw_text="+40 to Maximum Life"),
            ItemMod(raw_text="+20% to Fire Resistance"),
        ],  # Only 2 affixes, open crafts
        verification=VerificationState.VERIFIED,
    )
    gear_state = GearAuditState(character_id="hero", slots={ItemSlot.HELMET: helm})
    gear_adv = evaluate_gear_rules(gear_state=gear_state, character_level=68)
    assert any(a.code == "GEAR_OPEN_CRAFT" for a in gear_adv)
    assert any(a.code == "GEAR_BASE_OUTDATED" for a in gear_adv)

    # 3. Troubleshooting diagnostics
    trouble_adv = evaluate_troubleshooting_rules(
        character_attributes={"str": 100, "dex": 50, "int": 52},
        required_attributes={"str": 80, "dex": 55, "int": 50},  # dex deficit of 5, int margin 2
        current_mana=600,
        unreserved_mana=25,  # 25 unreserved
        main_skill_cost=20,  # 20 cost requires 40 buffer
    )
    assert any(a.code == "MANA_STARVATION" and a.severity == AdvisorySeverity.CRITICAL for a in trouble_adv)
    assert any(a.code == "ATTRIBUTE_DEFICIT_DEX" and a.severity == AdvisorySeverity.CRITICAL for a in trouble_adv)
    assert any(a.code == "ATTRIBUTE_TIGHT_INT" and a.severity == AdvisorySeverity.WARNING for a in trouble_adv)

    # 4. Story quest progression guidance
    story_adv = evaluate_story_progression(current_act=4, completed_quest_ids={"act1_caravan"})
    assert any(a.code == "STORY_MISSED_PERMANENT_REWARD" and "spirit" in a.description.lower() for a in story_adv)

    # 5. Economy prioritization with uncapped cold resistance
    is_res_capped = not any(a.code.startswith("RES_UNCAPPED_") for a in survival_adv)
    assert is_res_capped is False
    priorities = evaluate_economy_priorities(
        character_level=68,
        current_resists_capped=is_res_capped,
        weapon_dps_lagging=True,
    )
    assert priorities[0].priority_tier == 1
    assert "resist" in priorities[0].roi_reason.lower()
