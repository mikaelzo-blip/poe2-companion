"""Unit tests for Milestone 9 gear rules and troubleshooting diagnostics."""

import pytest
from companion.gear.schema import EquippedItem, GearAuditState, ItemMod, ItemRarity, ItemSlot
from companion.intelligence.gear_rules import evaluate_gear_rules
from companion.intelligence.schema import AdvisoryCategory, AdvisorySeverity
from companion.intelligence.troubleshooting import evaluate_troubleshooting_rules
from companion.state.provenance import VerificationState


def test_gear_rules_open_craft_and_outdated_base() -> None:
    boots = EquippedItem(
        slot=ItemSlot.BOOTS,
        name="Storm Tread",
        base_type="Iron Greaves",
        rarity=ItemRarity.RARE,
        item_level=20,  # 35 levels below char level 55
        explicit_mods=[
            ItemMod(raw_text="+30 to Maximum Life"),
            ItemMod(raw_text="+15% to Cold Resistance"),
        ],  # 2 mods, open crafts
        verification=VerificationState.VERIFIED,
    )
    gear_state = GearAuditState(character_id="test_char", slots={ItemSlot.BOOTS: boots})

    advisories = evaluate_gear_rules(gear_state=gear_state, character_level=55)

    # Should detect open crafts
    open_crafts = [a for a in advisories if a.code == "GEAR_OPEN_CRAFT"]
    assert len(open_crafts) == 1
    assert open_crafts[0].severity == AdvisorySeverity.INFO

    # Should detect outdated base
    outdated = [a for a in advisories if a.code == "GEAR_BASE_OUTDATED"]
    assert len(outdated) == 1
    assert outdated[0].severity == AdvisorySeverity.WARNING


def test_troubleshooting_mana_starvation() -> None:
    advisories = evaluate_troubleshooting_rules(
        character_attributes={"str": 100, "dex": 100, "int": 100},
        required_attributes={"str": 80, "dex": 80, "int": 80},
        current_mana=500,
        unreserved_mana=30,  # only 30 unreserved
        main_skill_cost=25,  # 25 cost -> requires 50+ for safe buffer
    )
    starvation = [a for a in advisories if a.code == "MANA_STARVATION"]
    assert len(starvation) == 1
    assert starvation[0].severity == AdvisorySeverity.CRITICAL


def test_troubleshooting_attribute_deficit_and_tight() -> None:
    advisories = evaluate_troubleshooting_rules(
        character_attributes={"str": 50, "dex": 102, "int": 100},
        required_attributes={"str": 55, "dex": 100, "int": 80},  # str missing 5, dex margin 2
        current_mana=500,
        unreserved_mana=200,
        main_skill_cost=20,
    )
    deficit = [a for a in advisories if a.code == "ATTRIBUTE_DEFICIT_STR"]
    assert len(deficit) == 1
    assert deficit[0].severity == AdvisorySeverity.CRITICAL

    tight = [a for a in advisories if a.code == "ATTRIBUTE_TIGHT_DEX"]
    assert len(tight) == 1
    assert tight[0].severity == AdvisorySeverity.WARNING
