"""Unit tests for Milestone 9 gear rules and troubleshooting diagnostics."""

import pytest
from companion.gear.schema import EquippedItem, GearAuditState, ItemMod, ItemRarity, ItemSlot
from companion.intelligence.gear_rules import evaluate_gear_rules
from companion.intelligence.schema import (
    AdvisoryCategory,
    AdvisorySeverity,
    ProvenanceCategory,
)
from companion.intelligence.troubleshooting import (
    OperandEvidence,
    evaluate_troubleshooting_rules,
)
from companion.state.provenance import VerificationState


def test_gear_rules_heuristics_removed() -> None:
    """Invented rare affix count and outdated base tier heuristics are removed."""
    boots = EquippedItem(
        slot=ItemSlot.BOOTS,
        name="Storm Tread",
        base_type="Iron Greaves",
        rarity=ItemRarity.RARE,
        item_level=20,
        explicit_mods=[
            ItemMod(raw_text="+30 to Maximum Life"),
            ItemMod(raw_text="+15% to Cold Resistance"),
        ],
        verification=VerificationState.VERIFIED,
    )
    gear_state = GearAuditState(character_id="test_char", slots={ItemSlot.BOOTS: boots})

    advisories = evaluate_gear_rules(gear_state=gear_state, character_level=55)
    # Neither GEAR_OPEN_CRAFT nor GEAR_BASE_OUTDATED should be emitted
    assert not any(a.code == "GEAR_OPEN_CRAFT" for a in advisories)
    assert not any(a.code == "GEAR_BASE_OUTDATED" for a in advisories)
    assert len(advisories) == 0


def test_troubleshooting_mana_starvation_authoritative_when_verified() -> None:
    """True lockout (unreserved < cost) emits authoritative alert; 2x buffer is removed."""
    # 1. True mechanical lockout (15 < 25)
    lockout_adv = evaluate_troubleshooting_rules(
        character_attributes={"str": 100, "dex": 100, "int": 100},
        required_attributes={"str": 80, "dex": 80, "int": 80},
        current_mana=500,
        unreserved_mana=15,
        main_skill_cost=25,
    )
    starvation = [a for a in lockout_adv if a.code == "MANA_STARVATION"]
    assert len(starvation) == 1
    assert starvation[0].severity == AdvisorySeverity.CRITICAL
    assert starvation[0].is_inference is False
    assert starvation[0].provenance == ProvenanceCategory.SOURCE_BACKED

    # 2. Arbitrary 2x buffer suppressed: 30 unreserved >= 25 cost (even though < 50)
    no_lockout_adv = evaluate_troubleshooting_rules(
        character_attributes={"str": 100, "dex": 100, "int": 100},
        required_attributes={"str": 80, "dex": 80, "int": 80},
        current_mana=500,
        unreserved_mana=30,
        main_skill_cost=25,
    )
    assert not any(a.code == "MANA_STARVATION" for a in no_lockout_adv)


def test_troubleshooting_mana_unknown_when_stale_or_missing() -> None:
    """Missing or stale operands suppress definitive mana lockout advisory."""
    # Operand UNKNOWN
    adv_unknown = evaluate_troubleshooting_rules(
        character_attributes={},
        required_attributes={},
        unreserved_mana=OperandEvidence(value=10, verification_state=VerificationState.UNKNOWN),
        main_skill_cost=25,
    )
    assert not any(a.code == "MANA_STARVATION" for a in adv_unknown)

    # Operand STALE
    adv_stale = evaluate_troubleshooting_rules(
        character_attributes={},
        required_attributes={},
        unreserved_mana=10,
        main_skill_cost=OperandEvidence(value=25, is_stale=True),
    )
    assert not any(a.code == "MANA_STARVATION" for a in adv_stale)


def test_troubleshooting_attribute_deficit_and_margin_removal() -> None:
    """Factual deficit is authoritative; arbitrary <5 margin is removed."""
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
    assert deficit[0].is_inference is False
    assert deficit[0].provenance == ProvenanceCategory.SOURCE_BACKED

    # Tight margin (<5) heuristic must NOT be emitted
    assert not any(a.code == "ATTRIBUTE_TIGHT_DEX" for a in advisories)


def test_troubleshooting_attribute_unknown_when_unverified_or_missing() -> None:
    """Missing or unverified attribute operands do not invent values and yield UNKNOWN."""
    # Missing attribute operand (not provided, must not default to 0)
    adv_missing = evaluate_troubleshooting_rules(
        character_attributes={},
        required_attributes={"str": 55},
    )
    assert not any(a.code.startswith("ATTRIBUTE_DEFICIT_") for a in adv_missing)

    # Unverified attribute operand
    adv_unverified = evaluate_troubleshooting_rules(
        character_attributes={"str": OperandEvidence(value=50, verification_state=VerificationState.UNKNOWN)},
        required_attributes={"str": 55},
    )
    assert not any(a.code.startswith("ATTRIBUTE_DEFICIT_") for a in adv_unverified)
