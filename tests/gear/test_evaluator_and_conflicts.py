"""Unit tests for gear comparison, TTL staleness, investment advice, and conflict detection."""

from datetime import datetime, timedelta, timezone
import pytest

from companion.gear.advisor import compare_candidate_upgrade, generate_investment_advice
from companion.gear.conflicts import ConflictType, detect_mechanic_conflicts
from companion.gear.evaluator import compare_equipped_against_target, evaluate_gear_staleness
from companion.gear.schema import ComparisonVerdict, EquippedItem, ItemMod, ItemSlot
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
        verification=VerificationState.VERIFIED,
    )

    # Missing verified target requirements
    target_reqs = {"life": 50, "fire_res": 20}
    advice = generate_investment_advice(equipped, target_requirements=target_reqs, upcoming_milestone_level=52)
    assert advice.needs_replacement is True
    assert "missing" in advice.recommendation.lower()
    assert "life" in advice.missing_requirements
    assert "fire_res" in advice.missing_requirements

    # Candidate meeting requirements
    candidate = EquippedItem(
        slot=ItemSlot.BODY_ARMOUR,
        base_type="Full Plate",
        level_req=48,
        explicit_mods=[
            ItemMod(raw_text="+75 to Maximum Life", key="life", value=75),
            ItemMod(raw_text="+30% to Fire Resistance", key="fire_res", value=30),
        ],
        verification=VerificationState.VERIFIED,
    )
    advice_good = generate_investment_advice(candidate, target_requirements=target_reqs, upcoming_milestone_level=52)
    assert advice_good.needs_replacement is False
    assert "satisfies" in advice_good.recommendation.lower()

    # Compare candidate upgrade against equipped with target requirements
    upg = compare_candidate_upgrade(equipped, candidate, target_requirements=target_reqs)
    assert upg.verdict == ComparisonVerdict.SATISFIES_MORE_VERIFIED_REQUIREMENTS
    assert "life" in upg.candidate_satisfied
    assert "fire_res" in upg.candidate_satisfied

    # Candidate without target requirements yields UNKNOWN
    upg_unknown = compare_candidate_upgrade(equipped, candidate, target_requirements={})
    assert upg_unknown.verdict == ComparisonVerdict.UNKNOWN

    # Candidate with unverified state yields UNKNOWN
    unverified_cand = candidate.model_copy(update={"verification": VerificationState.UNKNOWN})
    upg_unverified = compare_candidate_upgrade(equipped, unverified_cand, target_requirements=target_reqs)
    assert upg_unverified.verdict == ComparisonVerdict.UNKNOWN

    # Trade-off yields INCOMPARABLE
    cand_tradeoff = EquippedItem(
        slot=ItemSlot.BODY_ARMOUR,
        base_type="Full Plate",
        level_req=48,
        explicit_mods=[
            ItemMod(raw_text="+30% to Fire Resistance", key="fire_res", value=30),
        ],
        verification=VerificationState.VERIFIED,
    )
    upg_trade = compare_candidate_upgrade(
        equipped, cand_tradeoff, target_requirements={"life": 10, "fire_res": 20}
    )
    assert upg_trade.verdict == ComparisonVerdict.INCOMPARABLE
    assert "fire_res" in upg_trade.trade_offs.get("gained", "")
    assert "life" in upg_trade.trade_offs.get("lost", "")


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
