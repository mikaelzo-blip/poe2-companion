"""Dedicated tests for Stage-Aware Progression and Fubgun Fire Rule Semantics."""

import pytest
from companion.equipment.build_breaker import evaluate_candidate_build_safety
from companion.equipment.parser import parse_item_text
from companion.equipment.rules import (
    BuildBreakerCertainty,
    BuildProgressionStage,
    RuleSeverity,
)
from companion.equipment.schema import SlotType, WeaponSetContext

# Ring with harmful added fire damage to attacks
RING_ADDED_FIRE = """Item Class: Rings
Rarity: Rare
Ruby Ring
Iron Ring
--------
Requirements:
Level: 10
--------
Adds 4 to 9 Fire Damage to Attacks
+40 to maximum Life
+30% to Cold Resistance
"""

# Ring with non-harmful increased fire damage
RING_INC_FIRE = """Item Class: Rings
Rarity: Rare
Ember Band
Iron Ring
--------
Requirements:
Level: 10
--------
25% increased Fire Damage
+40 to maximum Life
"""

# Ring with fire resistance
RING_FIRE_RES = """Item Class: Rings
Rarity: Rare
Firebreak Band
Iron Ring
--------
Requirements:
Level: 10
--------
+35% to Fire Resistance
+40 to maximum Life
"""

# Set 2 Crossbow with flat fire damage
CROSSBOW_SET2_FIRE = """Item Class: Crossbows
Rarity: Rare
Infernal Crossbow
Bombard Crossbow
--------
Physical Damage: 30-75
--------
Requirements:
Level: 52
--------
Adds 4 to 9 Fire Damage to Attacks
"""

# Set 1 Staff with fire damage (Flameblast staff exception)
STAFF_SET1_FIRE = """Item Class: Two Hand Staves
Rarity: Rare
Volcano Pillar
Chiming Staff
--------
Physical Damage: 45-93
--------
Requirements:
Level: 52
--------
Adds 4 to 9 Fire Damage to Attacks
72% increased Fire Damage
"""


# Section 13: Full Snapshot Normalization and Properties Table-Driven Regression
@pytest.mark.parametrize(
    "alias,expected_stage,expected_campaign,expected_pre_swap,expected_post_swap",
    [
        ("lvl 1-14", BuildProgressionStage.LEVELING_1_14, True, True, False),
        ("lvl 15-32", BuildProgressionStage.LEVELING_15_32, True, True, False),
        ("lvl 33-51", BuildProgressionStage.LEVELING_33_51, True, True, False),
        ("lvl 52 Swap", BuildProgressionStage.SWAP_52, True, False, True),
        ("lvl 53-68", BuildProgressionStage.LEVELING_53_68, True, False, True),
        ("lvl 85", BuildProgressionStage.LEVEL_85, False, False, True),
        ("Endgame", BuildProgressionStage.ENDGAME, False, False, True),
        ("Mageblood", BuildProgressionStage.MAGEBLOOD, False, False, True),
        ("DoT Cap", BuildProgressionStage.DOT_CAP, False, False, True),
    ],
)
def test_full_snapshot_normalization_and_properties(
    alias: str,
    expected_stage: BuildProgressionStage,
    expected_campaign: bool,
    expected_pre_swap: bool,
    expected_post_swap: bool,
):
    stage = BuildProgressionStage(alias)
    assert stage == expected_stage
    assert stage.is_campaign is expected_campaign
    assert stage.is_pre_swap is expected_pre_swap
    assert stage.is_post_swap is expected_post_swap


# Section 12: Dedicated Level 52 Boundary Test
def test_level_52_boundary_normalization_and_fire_rejection():
    stage = BuildProgressionStage("lvl 52 Swap")
    assert stage == BuildProgressionStage.SWAP_52
    assert stage.is_pre_swap is False
    assert stage.is_post_swap is True
    assert stage.is_campaign is True

    # Harmful added fire on shared ring MUST be rejected at lvl 52 Swap
    ring = parse_item_text(RING_ADDED_FIRE, target_slot=SlotType.RING_1)
    ev = evaluate_candidate_build_safety(
        candidate=ring,
        slot=SlotType.RING_1,
        stage=stage,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER
    assert ev.severity == RuleSeverity.BUILD_BREAKER
    assert "oil grenade" in ev.reason.lower() or "ignite" in ev.reason.lower()


# Section 10: Required Fire Test Matrix Across All Progression Snapshots
@pytest.mark.parametrize(
    "stage_input,expected_certainty",
    [
        ("lvl 1-14", BuildBreakerCertainty.VERIFIED_SAFE),
        ("lvl 15-32", BuildBreakerCertainty.VERIFIED_SAFE),
        ("lvl 33-51", BuildBreakerCertainty.VERIFIED_SAFE),
        ("lvl 52 Swap", BuildBreakerCertainty.VERIFIED_BUILD_BREAKER),
        ("lvl 53-68", BuildBreakerCertainty.VERIFIED_BUILD_BREAKER),
        ("lvl 85", BuildBreakerCertainty.VERIFIED_BUILD_BREAKER),
        ("Endgame", BuildBreakerCertainty.VERIFIED_BUILD_BREAKER),
        ("Mageblood", BuildBreakerCertainty.VERIFIED_BUILD_BREAKER),
        ("DoT Cap", BuildBreakerCertainty.VERIFIED_BUILD_BREAKER),
    ],
)
def test_fire_matrix_shared_ring_added_fire(stage_input: str, expected_certainty: BuildBreakerCertainty):
    stage = BuildProgressionStage(stage_input)
    ring = parse_item_text(RING_ADDED_FIRE, target_slot=SlotType.RING_1)
    ev = evaluate_candidate_build_safety(
        candidate=ring,
        slot=SlotType.RING_1,
        stage=stage,
    )
    assert ev.certainty == expected_certainty
    if expected_certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER:
        assert ev.severity == RuleSeverity.BUILD_BREAKER
        assert "oil grenade" in ev.reason.lower() or "ignite" in ev.reason.lower()
    else:
        assert ev.certainty == BuildBreakerCertainty.VERIFIED_SAFE


# Section 11: Required Weapon-Context Tests at lvl 53-68
def test_weapon_context_lvl53_68_shared_ring():
    # A. shared ring harmful added Fire -> VERIFIED_BUILD_BREAKER
    stage = BuildProgressionStage("lvl 53-68")
    ring = parse_item_text(RING_ADDED_FIRE, target_slot=SlotType.RING_1)
    ev = evaluate_candidate_build_safety(
        candidate=ring,
        slot=SlotType.RING_1,
        stage=stage,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER
    assert ev.severity == RuleSeverity.BUILD_BREAKER


def test_weapon_context_lvl53_68_set2_crossbow():
    # B. Set 2 Oil Grenade crossbow harmful applicable added Fire -> VERIFIED_BUILD_BREAKER
    stage = BuildProgressionStage("lvl 53-68")
    crossbow = parse_item_text(
        CROSSBOW_SET2_FIRE,
        target_slot=SlotType.MAIN_HAND,
        target_weapon_set=WeaponSetContext.WEAPON_SET_2,
    )
    ev = evaluate_candidate_build_safety(
        candidate=crossbow,
        slot=SlotType.MAIN_HAND,
        weapon_set=WeaponSetContext.WEAPON_SET_2,
        stage=stage,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER
    assert ev.severity == RuleSeverity.BUILD_BREAKER


def test_weapon_context_lvl53_68_set1_staff_exception():
    # C. Set 1 Flameblast staff covered by verified exception -> not rejected solely by this rule
    # Must prove C passes through the weapon-set exception, not through campaign short-circuiting.
    from companion.equipment.fubgun_rules import evaluate_fubgun_modifier

    stage = BuildProgressionStage("lvl 53-68")
    staff = parse_item_text(
        STAFF_SET1_FIRE,
        target_slot=SlotType.MAIN_HAND,
        target_weapon_set=WeaponSetContext.WEAPON_SET_1,
    )
    # Direct modifier evaluation proves weapon set 1 exception branch is reached and exercised
    cert, sev, reason = evaluate_fubgun_modifier(
        mod=staff.modifiers[0],
        slot=SlotType.MAIN_HAND,
        weapon_set=WeaponSetContext.WEAPON_SET_1,
        stage=stage,
    )
    assert cert == BuildBreakerCertainty.VERIFIED_SAFE
    assert sev == RuleSeverity.INFO
    assert "weapon set 1" in reason.lower() or "flameblast staff" in reason.lower()
    assert "pre-swap" not in reason.lower()

    # Full candidate evaluation passes
    ev = evaluate_candidate_build_safety(
        candidate=staff,
        slot=SlotType.MAIN_HAND,
        weapon_set=WeaponSetContext.WEAPON_SET_1,
        stage=stage,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_SAFE
    assert ev.severity == RuleSeverity.INFO


# Section 6: Preserve % increased Fire Damage and Fire Resistance as Safe
def test_fire_non_harmful_modifiers_preserved():
    for stage_alias in ("lvl 52 Swap", "lvl 53-68", "Endgame"):
        stage = BuildProgressionStage(stage_alias)

        # % increased Fire Damage
        ring_inc = parse_item_text(RING_INC_FIRE, target_slot=SlotType.RING_1)
        ev_inc = evaluate_candidate_build_safety(
            candidate=ring_inc,
            slot=SlotType.RING_1,
            stage=stage,
        )
        assert ev_inc.certainty == BuildBreakerCertainty.VERIFIED_SAFE

        # Fire Resistance
        ring_res = parse_item_text(RING_FIRE_RES, target_slot=SlotType.RING_1)
        ev_res = evaluate_candidate_build_safety(
            candidate=ring_res,
            slot=SlotType.RING_1,
            stage=stage,
        )
        assert ev_res.certainty == BuildBreakerCertainty.VERIFIED_SAFE
