"""Forensic verification tests covering items A through F before commit."""

from pathlib import Path
import pytest
from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.build_breaker import evaluate_candidate_build_safety
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.fubgun_rules import evaluate_fubgun_modifier
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.equipment.parser import parse_item_text
from companion.equipment.precedence import Verdict
from companion.equipment.rules import (
    BuildBreakerCertainty,
    BuildProgressionStage,
    RuleSeverity,
)
from companion.equipment.schema import SlotType, WeaponSetContext

RING_ADDED_FIRE = """Item Class: Rings
Rarity: Rare
Pyre Band
Iron Ring
--------
Requirements:
Level: 10
--------
Adds 4 to 9 Fire Damage to Attacks
+40 to maximum Life
+30% to Cold Resistance
"""

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

CAMPAIGN_BOOTS_LIFE_MS = """Item Class: Boots
Rarity: Rare
Fleet Stride
Wrapped Boots
--------
Requirements:
Level: 22
--------
+70 to maximum Life
+25% increased Movement Speed
"""


def test_forensic_a_lvl15_32_shared_ring_added_fire_safe():
    """A. lvl 15-32 + harmful shared added Fire -> pre-swap safe from THIS post-swap rule."""
    stage = BuildProgressionStage("lvl 15-32")
    ring = parse_item_text(RING_ADDED_FIRE, target_slot=SlotType.RING_1)
    ev = evaluate_candidate_build_safety(
        candidate=ring,
        slot=SlotType.RING_1,
        stage=stage,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_SAFE
    assert ev.severity == RuleSeverity.INFO


def test_forensic_b_lvl52_swap_shared_ring_added_fire_build_breaker():
    """B. lvl 52 Swap + same modifier -> build breaker."""
    stage = BuildProgressionStage("lvl 52 Swap")
    ring = parse_item_text(RING_ADDED_FIRE, target_slot=SlotType.RING_1)
    ev = evaluate_candidate_build_safety(
        candidate=ring,
        slot=SlotType.RING_1,
        stage=stage,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER
    assert ev.severity == RuleSeverity.BUILD_BREAKER
    assert "oil grenade" in ev.reason.lower() or "ignite" in ev.reason.lower()


def test_forensic_c_lvl53_68_shared_ring_added_fire_build_breaker():
    """C. lvl 53-68 + same modifier -> build breaker."""
    stage = BuildProgressionStage("lvl 53-68")
    ring = parse_item_text(RING_ADDED_FIRE, target_slot=SlotType.RING_1)
    ev = evaluate_candidate_build_safety(
        candidate=ring,
        slot=SlotType.RING_1,
        stage=stage,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER
    assert ev.severity == RuleSeverity.BUILD_BREAKER
    assert "oil grenade" in ev.reason.lower() or "ignite" in ev.reason.lower()


def test_forensic_d_lvl53_68_set2_crossbow_build_breaker():
    """D. lvl 53-68 Set2 crossbow harmful Fire -> build breaker."""
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


def test_forensic_e_lvl53_68_set1_staff_exception_reached():
    """E. lvl 53-68 Set1 staff verified exception -> exception branch reached."""
    stage = BuildProgressionStage("lvl 53-68")
    staff = parse_item_text(
        STAFF_SET1_FIRE,
        target_slot=SlotType.MAIN_HAND,
        target_weapon_set=WeaponSetContext.WEAPON_SET_1,
    )
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


def test_forensic_f_lvl15_32_life_ms_boots_not_blocked(tmp_path: Path):
    """F. lvl 15-32 strong Life/MS candidate with unchanged low resistance -> not blocked solely by reference-cap gaps."""
    runtime_dir = tmp_path / "runtime"
    char_id = "forensic_f_char"

    run_loadout_set_item(
        runtime_dir,
        char_id,
        "boots",
        "Item Class: Boots\nRarity: Normal\nRough Boots\n--------\n",
    )
    run_loadout_finalize(runtime_dir, char_id)

    run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=300,
        fire_res=15,
        fire_raw=15,
        cold_res=0,
        cold_raw=0,
        lightning_res=7,
        lightning_raw=7,
        chaos_res=0,
        dex=50,
        int=50,
        str=50,
    )

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        item_text=CAMPAIGN_BOOTS_LIFE_MS,
        character_id=char_id,
        stage="lvl 15-32",
    )

    assert rec.verdict == Verdict.EQUIP_NOW
    assert "UNCHANGED_CRITICAL_DEFICIT" not in rec.flags
    assert rec.contextual_analysis.has_unchanged_critical_deficiency is False
    assert rec.contextual_analysis.has_unresolved_resistance_priority is True
