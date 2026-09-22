"""Unit tests for gear comparison, TTL staleness, investment advice, and conflict detection."""

from datetime import datetime, timedelta, timezone
import pytest

from companion.gear.advisor import compare_candidate_upgrade, generate_investment_advice
from companion.gear.conflicts import ConflictType, detect_mechanic_conflicts
from companion.gear.evaluator import compare_equipped_against_target, evaluate_gear_staleness
from companion.gear.schema import EquippedItem, ItemMod, ItemRarity, ItemSlot
from companion.state.provenance import VerificationState


def test_gear_staleness_ttl() -> None:
    now = datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)
    fresh_time = now - timedelta(minutes=15)
    stale_time = now - timedelta(minutes=90)

    fresh_item = EquippedItem(
        slot=ItemSlot.BOOTS,
        base_type="Iron Greaves",
        observed_at=fresh_time.isoformat(),
        verification=VerificationState.VERIFIED,
    )
    stale_item = EquippedItem(
        slot=ItemSlot.BOOTS,
        base_type="Iron Greaves",
        observed_at=stale_time.isoformat(),
        verification=VerificationState.VERIFIED,
    )

    assert evaluate_gear_staleness(fresh_item, now=now, ttl_minutes=60) == VerificationState.VERIFIED
    assert evaluate_gear_staleness(stale_item, now=now, ttl_minutes=60) == VerificationState.STALE


def test_compare_equipped_against_target() -> None:
    item = EquippedItem(
        slot=ItemSlot.HELMET,
        base_type="Iron Helmet",
        explicit_mods=[
            ItemMod(raw_text="+40 to Maximum Life", key="life", value=40),
            ItemMod(raw_text="+20% to Fire Resistance", key="fire_res", value=20),
        ],
        verification=VerificationState.VERIFIED,
    )

    # Target requires life and fire_res
    target_reqs = {"life": 30, "fire_res": 15}
    comp = compare_equipped_against_target(item, target_reqs)
    assert comp.is_compliant is True
    assert len(comp.missing_requirements) == 0

    # Target requires cold_res which is missing
    target_reqs_strict = {"life": 30, "cold_res": 20}
    comp_strict = compare_equipped_against_target(item, target_reqs_strict)
    assert comp_strict.is_compliant is False
    assert "cold_res" in comp_strict.missing_requirements


def test_investment_advice_and_upgrade_comparison() -> None:
    equipped = EquippedItem(
        slot=ItemSlot.BODY_ARMOUR,
        base_type="Plate Vest",
        level_req=10,
        explicit_mods=[ItemMod(raw_text="+20 to Maximum Life", key="life", value=20)],
    )

    # Next milestone is level 52; low level vest gets durability warning
    advice = generate_investment_advice(equipped, upcoming_milestone_level=52)
    assert advice.needs_replacement is True
    assert "durability" in advice.recommendation.lower()

    # Compare candidate upgrade against equipped
    candidate = EquippedItem(
        slot=ItemSlot.BODY_ARMOUR,
        base_type="Full Plate",
        level_req=48,
        explicit_mods=[
            ItemMod(raw_text="+75 to Maximum Life", key="life", value=75),
            ItemMod(raw_text="+30% to Fire Resistance", key="fire_res", value=30),
        ],
    )
    upg = compare_candidate_upgrade(equipped, candidate)
    assert upg.action == "UPGRADE"
    assert upg.score_delta > 0


def test_mechanic_conflict_detection() -> None:
    char_stats = {"str": 40, "dex": 80, "int": 50}

    # Item requires 70 Str, character has 40
    item = EquippedItem(
        slot=ItemSlot.MAIN_HAND,
        base_type="Two Handed Axe",
        required_str=70,
    )

    conflicts = detect_mechanic_conflicts(
        item,
        character_attributes=char_stats,
        target_weapon_archetype="bow",
    )

    assert len(conflicts) == 2
    types = [c.conflict_type for c in conflicts]
    assert ConflictType.UNMET_ATTRIBUTE in types
    assert ConflictType.WEAPON_ARCHETYPE_MISMATCH in types
