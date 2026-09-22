"""End-to-end integration test for Milestone 9 expanded build intelligence pipeline."""

from pathlib import Path
import pytest

from companion.gear.schema import EquippedItem, GearAuditState, ItemMod, ItemRarity, ItemSlot
from companion.intelligence import (
    AdvisoryCategory,
    AdvisorySeverity,
    ProvenanceCategory,
    evaluate_economy_priorities,
    evaluate_gear_rules,
    evaluate_story_progression,
    evaluate_survival_rules,
    evaluate_troubleshooting_rules,
    get_economy_deferred_notice,
    get_story_deferred_notice,
    get_story_quests,
)
from companion.state.provenance import VerificationState
from companion.vision.schema import CharacterPanelStats


def test_m9_expanded_intelligence_end_to_end_pipeline() -> None:
    # 1. Survival rules evaluation with real observed panel stats (labeled inference for 75% cap)
    panel_stats = CharacterPanelStats(
        life=1900,
        mana=600,
        spirit=120,
        fire_res=75,
        cold_res=50,  # Uncapped in maps
        lightning_res=75,
        chaos_res=-40,
        armour=2200,
        evasion=1100,
    )
    survival_adv = evaluate_survival_rules(panel_stats=panel_stats, character_level=68, current_act=7)
    cold_adv = [a for a in survival_adv if a.code == "RES_UNCAPPED_COLD"]
    assert len(cold_adv) == 1
    assert cold_adv[0].is_inference is True
    assert cold_adv[0].provenance == ProvenanceCategory.LABELED_INFERENCE

    # Verify pruned heuristics do NOT appear
    assert not any(a.code == "CHAOS_RES_LOW" for a in survival_adv)
    assert not any(a.code.startswith("LIFE_POOL_") for a in survival_adv)

    # 2. Gear rules evaluation with audited gear state (heuristics pruned)
    helm = EquippedItem(
        slot=ItemSlot.HELMET,
        name="Crown of Thorns",
        base_type="Iron Helmet",
        rarity=ItemRarity.RARE,
        item_level=30,
        explicit_mods=[
            ItemMod(raw_text="+40 to Maximum Life"),
            ItemMod(raw_text="+20% to Fire Resistance"),
        ],
        verification=VerificationState.VERIFIED,
    )
    gear_state = GearAuditState(character_id="hero", slots={ItemSlot.HELMET: helm})
    gear_adv = evaluate_gear_rules(gear_state=gear_state, character_level=68)
    assert not any(a.code == "GEAR_OPEN_CRAFT" for a in gear_adv)
    assert not any(a.code == "GEAR_BASE_OUTDATED" for a in gear_adv)
    assert len(gear_adv) == 0

    # 3. Troubleshooting diagnostics with true deficits (buffers removed)
    trouble_adv = evaluate_troubleshooting_rules(
        character_attributes={"str": 100, "dex": 50, "int": 52},
        required_attributes={"str": 80, "dex": 55, "int": 50},  # dex deficit of 5, int meets req (52 >= 50)
        current_mana=600,
        unreserved_mana=15,  # 15 unreserved is strictly less than 20 cost -> lockout
        main_skill_cost=20,
    )
    assert any(a.code == "MANA_STARVATION" and a.severity == AdvisorySeverity.CRITICAL for a in trouble_adv)
    assert any(a.code == "ATTRIBUTE_DEFICIT_DEX" and a.severity == AdvisorySeverity.CRITICAL for a in trouble_adv)
    # Tight attribute margin (<5) heuristic must NOT be emitted
    assert not any(a.code == "ATTRIBUTE_TIGHT_INT" for a in trouble_adv)

    # 4. Story quest progression guidance is deferred per Blueprint Section 62
    story_adv = evaluate_story_progression(current_act=4, completed_quest_ids={"act1_caravan"})
    assert any(a.code == "STORY_FEATURE_DEFERRED" for a in story_adv)
    assert story_adv[0].provenance == ProvenanceCategory.DEFERRED_BY_BLUEPRINT
    notice_story = get_story_deferred_notice()
    assert notice_story["status"] == "DEFERRED_BY_BLUEPRINT"

    # 5. Economy prioritization is deferred per Blueprint Section 62
    priorities = evaluate_economy_priorities(
        character_level=68,
        current_resists_capped=False,
        weapon_dps_lagging=True,
    )
    assert priorities == []
    notice_econ = get_economy_deferred_notice()
    assert notice_econ["status"] == "DEFERRED_BY_BLUEPRINT"
