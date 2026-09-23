"""Unit tests for the exact Fubgun Flameblast/Oil Grenade Fire rule."""

import pytest
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.equipment.parser import parse_item_text
from companion.equipment.rules import (
    BuildBreakerCertainty,
    BuildProgressionStage,
    RuleSeverity,
)
from companion.equipment.build_breaker import evaluate_candidate_build_safety

RING_FLAT_FIRE_ATTACK = """Item Class: Rings
Rarity: Rare
Pyre Band
Iron Ring
--------
Requirements:
Level: 40
--------
Adds 12 to 24 Fire Damage to Attacks
+40 to maximum Life
+30% to Cold Resistance
"""

RING_INCREASED_FIRE = """Item Class: Rings
Rarity: Rare
Ember Band
Iron Ring
--------
Requirements:
Level: 40
--------
25% increased Fire Damage
+40 to maximum Life
"""

AMULET_FLAT_FIRE_SPELL = """Item Class: Amulets
Rarity: Rare
Blaze Choker
Paua Amulet
--------
Requirements:
Level: 40
--------
Adds 10 to 20 Fire Damage to Spells
+30 to maximum Life
"""

STAFF_FIRE = """Item Class: Two Hand Staves
Rarity: Rare
Volcano Pillar
Chiming Staff
--------
Physical Damage: 45-93
--------
Requirements:
Level: 52
--------
Adds 15 to 30 Fire Damage to Attacks
72% increased Fire Damage
"""

CROSSBOW_FIRE = """Item Class: Crossbows
Rarity: Rare
Infernal Crossbow
Bombard Crossbow
--------
Physical Damage: 30-75
--------
Requirements:
Level: 52
--------
Adds 10 to 20 Fire Damage to Attacks
"""


def test_flat_fire_attack_on_ring_in_early_endgame_is_build_breaker():
    ring = parse_item_text(RING_FLAT_FIRE_ATTACK, target_slot=SlotType.RING_1)
    ev = evaluate_candidate_build_safety(
        candidate=ring,
        slot=SlotType.RING_1,
        stage=BuildProgressionStage.EARLY_ENDGAME,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER
    assert ev.severity == RuleSeverity.BUILD_BREAKER
    assert "oil grenade" in ev.reason.lower() or "ignite" in ev.reason.lower()


def test_flat_fire_attack_on_ring_in_pre_swap_is_safe():
    ring = parse_item_text(RING_FLAT_FIRE_ATTACK, target_slot=SlotType.RING_1)
    ev = evaluate_candidate_build_safety(
        candidate=ring,
        slot=SlotType.RING_1,
        stage=BuildProgressionStage.PRE_SWAP,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_SAFE


def test_staff_with_fire_in_weapon_set_1_is_exempt():
    staff = parse_item_text(STAFF_FIRE, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_1)
    ev = evaluate_candidate_build_safety(
        candidate=staff,
        slot=SlotType.MAIN_HAND,
        weapon_set=WeaponSetContext.WEAPON_SET_1,
        stage=BuildProgressionStage.EARLY_ENDGAME,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_SAFE


def test_crossbow_with_flat_fire_in_weapon_set_2_is_build_breaker():
    crossbow = parse_item_text(CROSSBOW_FIRE, target_slot=SlotType.MAIN_HAND, target_weapon_set=WeaponSetContext.WEAPON_SET_2)
    ev = evaluate_candidate_build_safety(
        candidate=crossbow,
        slot=SlotType.MAIN_HAND,
        weapon_set=WeaponSetContext.WEAPON_SET_2,
        stage=BuildProgressionStage.EARLY_ENDGAME,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER


def test_increased_fire_damage_percent_is_safe():
    ring = parse_item_text(RING_INCREASED_FIRE, target_slot=SlotType.RING_1)
    ev = evaluate_candidate_build_safety(
        candidate=ring,
        slot=SlotType.RING_1,
        stage=BuildProgressionStage.EARLY_ENDGAME,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_SAFE


def test_flat_fire_spell_on_amulet_is_safe():
    amulet = parse_item_text(AMULET_FLAT_FIRE_SPELL, target_slot=SlotType.AMULET)
    ev = evaluate_candidate_build_safety(
        candidate=amulet,
        slot=SlotType.AMULET,
        stage=BuildProgressionStage.EARLY_ENDGAME,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_SAFE
