"""Unit tests for FubgunWeaponProfileRouter and build-specific weapon plan routing.

Enforces:
- Pre-swap vs Post-swap routing rules.
- Flameblast staff targeting Set 1 post-swap with fire spell exception.
- Oil Grenade crossbow targeting Set 2 post-swap with fire attack build-breaker rejection.
- Explicit WeaponSimulationContext creation.
- Rejection of weapons outside the Fubgun weapon plan (Bows, 2H Axes, Quivers).
"""

import pytest
from companion.equipment.parser import parse_item_text
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.equipment.fubgun_weapon_router import (
    FubgunWeaponProfileRouter,
    FubgunWeaponRoutingResult,
    WeaponSimulationContext,
)
from companion.equipment.weapon_topology import WeaponArchetype

STAFF_TEXT = """Item Class: Two Hand Staves
Rarity: Rare
Volcano Pillar
Chiming Staff
--------
Physical Damage: 45-93
--------
Requirements:
Level: 52
--------
+20% to Fire Resistance
+2 to Level of all Fire Spell Skill Gems
Adds 15 to 30 Fire Damage to Spells
"""

CROSSBOW_SAFE_TEXT = """Item Class: Crossbows
Rarity: Rare
Gloom Piercer
Bombard Crossbow
--------
Physical Damage: 30-75
--------
Requirements:
Level: 52
--------
+15% to Attack Speed
Adds 10 to 20 Physical Damage
"""

CROSSBOW_FLAT_FIRE_TEXT = """Item Class: Crossbows
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
+15% to Attack Speed
"""

BOW_TEXT = """Item Class: Bows
Rarity: Rare
Wind Bow
Short Bow
--------
Requirements:
Level: 30
--------
+10 to Dexterity
"""

QUIVER_TEXT = """Item Class: Quivers
Rarity: Rare
Eagle Flight
Broadhead Arrow Quiver
--------
Requirements:
Level: 45
--------
Adds 5 to 10 Physical Damage to Bow Attacks
"""


def test_preswap_routes_crossbow_to_set_1():
    router = FubgunWeaponProfileRouter()
    xbow = parse_item_text(CROSSBOW_SAFE_TEXT)

    result = router.route_candidate(
        candidate=xbow,
        stage=BuildProgressionStage.LEVELING_15_32,
        raw_text=CROSSBOW_SAFE_TEXT,
    )

    assert result.is_valid is True
    assert result.target_set == WeaponSetContext.WEAPON_SET_1
    assert result.target_slot == "Weapon 1"
    assert result.skill_context == "CROSSBOW_LEVELING"
    assert result.weapon_archetype == WeaponArchetype.TWO_HAND_CROSSBOW
    assert isinstance(result.context, WeaponSimulationContext)


def test_preswap_lvl17_does_not_falsely_depend_on_postswap_oil_grenade_semantics():
    """Level 17 (LEVELING_15_32) Crossbow must resolve CROSSBOW_LEVELING and not be rejected by post-swap flat fire."""
    router = FubgunWeaponProfileRouter()
    # Crossbow with flat fire (like BOMSHAK's actual Dire Core)
    xbow_with_fire = parse_item_text(CROSSBOW_FLAT_FIRE_TEXT)

    result = router.route_candidate(
        candidate=xbow_with_fire,
        stage=BuildProgressionStage.LEVELING_15_32,
        raw_text=CROSSBOW_FLAT_FIRE_TEXT,
    )

    assert result.is_valid is True
    assert result.target_set == WeaponSetContext.WEAPON_SET_1
    assert result.target_slot == "Weapon 1"
    assert result.skill_context == "CROSSBOW_LEVELING"
    assert "BUILD BREAKER" not in result.rejection_reason


def test_preswap_rejects_staff():
    router = FubgunWeaponProfileRouter()
    staff = parse_item_text(STAFF_TEXT)

    result = router.route_candidate(
        candidate=staff,
        stage=BuildProgressionStage.LEVELING_15_32,
        raw_text=STAFF_TEXT,
    )

    assert result.is_valid is False
    assert "post-swap" in result.rejection_reason.lower() or "52" in result.rejection_reason.lower()
    assert result.context is None


def test_postswap_routes_staff_to_set_1_flameblast():
    router = FubgunWeaponProfileRouter()
    staff = parse_item_text(STAFF_TEXT)

    result = router.route_candidate(
        candidate=staff,
        stage=BuildProgressionStage.SWAP_52,
        raw_text=STAFF_TEXT,
    )

    assert result.is_valid is True
    assert result.target_set == WeaponSetContext.WEAPON_SET_1
    assert result.target_slot == "Weapon 1"
    assert result.skill_context == "Flameblast"
    assert result.weapon_archetype == WeaponArchetype.TWO_HAND_STAFF


def test_postswap_routes_crossbow_to_set_2_oil_grenade():
    router = FubgunWeaponProfileRouter()
    xbow = parse_item_text(CROSSBOW_SAFE_TEXT)

    result = router.route_candidate(
        candidate=xbow,
        stage=BuildProgressionStage.SWAP_52,
        raw_text=CROSSBOW_SAFE_TEXT,
    )

    assert result.is_valid is True
    assert result.target_set == WeaponSetContext.WEAPON_SET_2
    assert result.target_slot == "Weapon 1 Swap"
    assert result.skill_context == "Oil Grenade"
    assert result.weapon_archetype == WeaponArchetype.TWO_HAND_CROSSBOW


def test_postswap_rejects_crossbow_with_flat_fire_as_build_breaker():
    router = FubgunWeaponProfileRouter()
    xbow_fire = parse_item_text(CROSSBOW_FLAT_FIRE_TEXT)

    result = router.route_candidate(
        candidate=xbow_fire,
        stage=BuildProgressionStage.SWAP_52,
        raw_text=CROSSBOW_FLAT_FIRE_TEXT,
    )

    assert result.is_valid is False
    assert "fire" in result.rejection_reason.lower()
    assert "oil grenade" in result.rejection_reason.lower() or "ignite" in result.rejection_reason.lower()


def test_fubgun_rejects_bow_and_quiver_across_all_stages():
    router = FubgunWeaponProfileRouter()
    bow = parse_item_text(BOW_TEXT)
    quiver = parse_item_text(QUIVER_TEXT)

    for stage in (BuildProgressionStage.LEVELING_15_32, BuildProgressionStage.SWAP_52, BuildProgressionStage.ENDGAME):
        res_bow = router.route_candidate(candidate=bow, stage=stage, raw_text=BOW_TEXT)
        assert res_bow.is_valid is False
        assert "bow" in res_bow.rejection_reason.lower()

        res_quiver = router.route_candidate(candidate=quiver, stage=stage, raw_text=QUIVER_TEXT)
        assert res_quiver.is_valid is False
        assert "quiver" in res_quiver.rejection_reason.lower()


def test_evaluate_fubgun_weapon_policy_equip_now():
    from companion.equipment.fubgun_priorities import evaluate_fubgun_weapon_policy
    from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
    from companion.equipment.precedence import Verdict

    delta = PobEquipmentDelta(
        slot="Weapon 1",
        candidate_id=1,
        candidate_name="Volcano Pillar",
        dps_delta=25.5,
        life_delta=30,
        fire_res_delta=15,
    )
    rec = evaluate_fubgun_weapon_policy(delta, skill_context="Flameblast")
    assert rec.verdict == Verdict.EQUIP_NOW
    assert "DPS upgrade" in rec.reason
    assert "+25.50 DPS" in rec.formatted_output
    assert "+30 Life" in rec.formatted_output


def test_evaluate_fubgun_weapon_policy_reject_dps_loss():
    from companion.equipment.fubgun_priorities import evaluate_fubgun_weapon_policy
    from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
    from companion.equipment.precedence import Verdict

    delta = PobEquipmentDelta(
        slot="Weapon 1",
        candidate_id=2,
        candidate_name="Weak Wand",
        dps_delta=-10.0,
        life_delta=20,
    )
    rec = evaluate_fubgun_weapon_policy(delta)
    assert rec.verdict == Verdict.REJECT
    assert "no DPS upgrade" in rec.reason


def test_evaluate_dual_weapon_policy():
    from companion.equipment.fubgun_priorities import evaluate_dual_weapon_policy
    from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta

    delta1 = PobEquipmentDelta(
        slot="Weapon 1",
        candidate_id=3,
        candidate_name="Opal Wand",
        dps_delta=15.0,
        life_delta=20,
    )
    delta2 = PobEquipmentDelta(
        slot="Weapon 2",
        candidate_id=3,
        candidate_name="Opal Wand",
        dps_delta=-5.0,
        life_delta=-10,
    )
    rec = evaluate_dual_weapon_policy(delta1, delta2)
    assert rec.recommended_slot == "Weapon 1"
    assert "Vs Weapon 1" in rec.formatted_output
    assert "Vs Weapon 2" in rec.formatted_output
