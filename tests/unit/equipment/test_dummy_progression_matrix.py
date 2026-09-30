"""Comprehensive dummy progression matrix tests across all build progression stages and equipment slots.

Verifies:
1. Life dimension (gain, loss, neutral)
2. Resistance dimension (single, multi, chaos, trade-offs)
3. Defense & EHP dimension (minor vs severe EHP loss, secondary gains)
4. Movement speed dimension (boots)
5. Weapon DPS dimension (pure gain, dps vs defense trade-offs, dps loss)
6. Dual-ring policy with empty slots and Pareto dominance
7. Dual-weapon policy with empty slots and DPS/defense balance
8. Build-breaker safety rules across pre-swap and post-swap stages
9. Requirements & attribute cascades
"""

import pytest
from companion.equipment.build_breaker import evaluate_candidate_build_safety
from companion.equipment.fubgun_priorities import (
    evaluate_dual_ring_policy,
    evaluate_dual_weapon_policy,
    evaluate_fubgun_equipment_policy,
    evaluate_fubgun_helmet_policy,
    evaluate_fubgun_weapon_policy,
)
from companion.equipment.parser import parse_item_text
from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
from companion.equipment.precedence import Verdict
from companion.equipment.rules import (
    BuildBreakerCertainty,
    BuildProgressionStage,
    RuleSeverity,
)
from companion.equipment.schema import SlotType, WeaponSetContext


ALL_PROGRESSION_STAGES = [
    BuildProgressionStage.LEVELING_1_14,
    BuildProgressionStage.LEVELING_15_32,
    BuildProgressionStage.LEVELING_33_51,
    BuildProgressionStage.SWAP_52,
    BuildProgressionStage.LEVELING_53_68,
    BuildProgressionStage.LEVEL_85,
    BuildProgressionStage.EARLY_ENDGAME,
    BuildProgressionStage.ENDGAME,
    BuildProgressionStage.MAGEBLOOD,
    BuildProgressionStage.DOT_CAP,
]

CORE_ARMOR_SLOTS = ["Helmet", "Body Armour", "Gloves", "Boots"]
JEWELRY_SLOTS = ["Belt", "Amulet", "Ring 1", "Ring 2"]
WEAPON_SLOTS = ["Weapon 1", "Weapon 2", "Weapon 1 Swap", "Weapon 2 Swap"]


# =============================================================================
# 1. LIFE DIMENSION TESTS ACROSS ALL STAGES
# =============================================================================

@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
@pytest.mark.parametrize("slot", CORE_ARMOR_SLOTS + JEWELRY_SLOTS)
def test_dummy_pure_life_gain_recommends_equip_now(stage: BuildProgressionStage, slot: str) -> None:
    delta = PobEquipmentDelta(
        slot=slot,
        candidate_id=101,
        candidate_name="Dummy Life Upgrade",
        life_delta=45,
        ehp_delta=3.2,
    )
    rec = evaluate_fubgun_equipment_policy(delta, stage=stage)
    assert rec.verdict == Verdict.EQUIP_NOW
    assert any("Life" in g for g in rec.gains)
    assert rec.stage == stage


@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
@pytest.mark.parametrize("slot", CORE_ARMOR_SLOTS + JEWELRY_SLOTS)
def test_dummy_pure_life_loss_rejects(stage: BuildProgressionStage, slot: str) -> None:
    delta = PobEquipmentDelta(
        slot=slot,
        candidate_id=102,
        candidate_name="Dummy Life Downgrade",
        life_delta=-40,
        ehp_delta=-2.5,
    )
    rec = evaluate_fubgun_equipment_policy(delta, stage=stage)
    assert rec.verdict == Verdict.REJECT
    assert any("Life" in t for t in rec.trade_offs)


# =============================================================================
# 2. RESISTANCE DIMENSION TESTS ACROSS ALL STAGES
# =============================================================================

@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
@pytest.mark.parametrize("slot", CORE_ARMOR_SLOTS + JEWELRY_SLOTS)
def test_dummy_single_resistance_gain_recommends_equip_now(stage: BuildProgressionStage, slot: str) -> None:
    delta = PobEquipmentDelta(
        slot=slot,
        candidate_id=201,
        candidate_name="Dummy Fire Res Ring",
        fire_res_delta=35,
        ehp_delta=4.1,
    )
    rec = evaluate_fubgun_equipment_policy(delta, stage=stage)
    assert rec.verdict == Verdict.EQUIP_NOW
    assert any("Fire Res" in g for g in rec.gains)


@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
@pytest.mark.parametrize("slot", CORE_ARMOR_SLOTS + JEWELRY_SLOTS)
def test_dummy_chaos_resistance_is_treated_as_defensive_upgrade(stage: BuildProgressionStage, slot: str) -> None:
    delta = PobEquipmentDelta(
        slot=slot,
        candidate_id=202,
        candidate_name="Dummy Amethyst Item",
        chaos_res_delta=28,
        ehp_delta=2.0,
    )
    rec = evaluate_fubgun_equipment_policy(delta, stage=stage)
    assert rec.verdict == Verdict.EQUIP_NOW
    assert any("Chaos Res" in g for g in rec.gains)


@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
@pytest.mark.parametrize("slot", CORE_ARMOR_SLOTS + JEWELRY_SLOTS)
def test_dummy_resistance_trade_off_yields_conditional_upgrade(stage: BuildProgressionStage, slot: str) -> None:
    delta = PobEquipmentDelta(
        slot=slot,
        candidate_id=203,
        candidate_name="Dummy Res Shift",
        fire_res_delta=40,
        cold_res_delta=-30,
        ehp_delta=0.5,
    )
    rec = evaluate_fubgun_equipment_policy(delta, stage=stage)
    assert rec.verdict == Verdict.CONDITIONAL_UPGRADE
    assert any("Fire Res" in g for g in rec.gains)
    assert any("Cold Res" in t for t in rec.trade_offs)


# =============================================================================
# 3. DEFENSE & EHP DIMENSION TESTS ACROSS ALL STAGES
# =============================================================================

@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
@pytest.mark.parametrize("slot", CORE_ARMOR_SLOTS)
def test_dummy_minor_ehp_loss_with_primary_stats_equips_now(stage: BuildProgressionStage, slot: str) -> None:
    # Minor local defense drop (e.g. lost 30 ES, -3.49 EHP) with +35 Life & +25% Fire Res
    delta = PobEquipmentDelta(
        slot=slot,
        candidate_id=301,
        candidate_name="Skull Ward style Helm",
        life_delta=35,
        fire_res_delta=25,
        es_delta=-32,
        ehp_delta=-3.49,
    )
    rec = evaluate_fubgun_equipment_policy(delta, stage=stage)
    assert rec.verdict == Verdict.EQUIP_NOW


@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
@pytest.mark.parametrize("slot", CORE_ARMOR_SLOTS)
def test_dummy_major_ehp_loss_forces_conditional_upgrade(stage: BuildProgressionStage, slot: str) -> None:
    # Severe local defense loss (e.g. -18.5 EHP) forces player decision
    delta = PobEquipmentDelta(
        slot=slot,
        candidate_id=302,
        candidate_name="Severe Defense Drop Helm",
        life_delta=25,
        fire_res_delta=20,
        armour_delta=-350,
        ehp_delta=-18.5,
    )
    rec = evaluate_fubgun_equipment_policy(delta, stage=stage)
    assert rec.verdict == Verdict.CONDITIONAL_UPGRADE
    assert "significant local defense loss" in rec.reason.lower()


@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
@pytest.mark.parametrize("slot", CORE_ARMOR_SLOTS)
def test_dummy_secondary_defense_gain_without_primary_is_conditional(stage: BuildProgressionStage, slot: str) -> None:
    delta = PobEquipmentDelta(
        slot=slot,
        candidate_id=303,
        candidate_name="Pure Armour Boots",
        armour_delta=120,
        ehp_delta=8.5,
    )
    rec = evaluate_fubgun_equipment_policy(delta, stage=stage)
    assert rec.verdict == Verdict.CONDITIONAL_UPGRADE
    assert "secondary local-defense improvement" in rec.reason.lower() or "secondary local defense" in rec.reason.lower()


# =============================================================================
# 4. BOOTS MOVEMENT SPEED DIMENSION
# =============================================================================

@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
def test_dummy_boots_movement_speed_gain_equips_now(stage: BuildProgressionStage) -> None:
    delta = PobEquipmentDelta(
        slot="Boots",
        candidate_id=401,
        candidate_name="Sprinter Boots",
        movement_speed_delta=20.0,
        life_delta=25,
    )
    rec = evaluate_fubgun_equipment_policy(delta, stage=stage)
    assert rec.verdict == Verdict.EQUIP_NOW


@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
def test_dummy_boots_movement_speed_loss_blocks_unconditional_equip_now(stage: BuildProgressionStage) -> None:
    delta = PobEquipmentDelta(
        slot="Boots",
        candidate_id=402,
        candidate_name="Heavy Iron Boots",
        movement_speed_delta=-15.0,
        life_delta=40,
    )
    rec = evaluate_fubgun_equipment_policy(delta, stage=stage)
    # Movement speed drop must NOT be an unconditional EQUIP_NOW
    assert rec.verdict == Verdict.CONDITIONAL_UPGRADE


# =============================================================================
# 5. WEAPON DPS & DEFENSE DIMENSION ACROSS ALL WEAPON SLOTS
# =============================================================================

@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
@pytest.mark.parametrize("slot", WEAPON_SLOTS)
def test_dummy_pure_weapon_dps_gain_equips_now(stage: BuildProgressionStage, slot: str) -> None:
    delta = PobEquipmentDelta(
        slot=slot,
        candidate_id=501,
        candidate_name="High DPS Crossbow",
        dps_delta=22.5,
    )
    rec = evaluate_fubgun_weapon_policy(delta, stage=stage)
    assert rec.verdict == Verdict.EQUIP_NOW
    assert any("DPS" in g for g in rec.gains)


@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
@pytest.mark.parametrize("slot", WEAPON_SLOTS)
def test_dummy_weapon_dps_gain_with_defensive_loss_is_conditional(stage: BuildProgressionStage, slot: str) -> None:
    delta = PobEquipmentDelta(
        slot=slot,
        candidate_id=502,
        candidate_name="Glass Cannon Wand",
        dps_delta=25.0,
        life_delta=-40,
        ehp_delta=-12.0,
    )
    rec = evaluate_fubgun_weapon_policy(delta, stage=stage)
    assert rec.verdict == Verdict.CONDITIONAL_UPGRADE
    assert "dps upgrade with defensive loss" in rec.reason.lower()


@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
@pytest.mark.parametrize("slot", WEAPON_SLOTS)
def test_dummy_weapon_dps_downgrade_rejects(stage: BuildProgressionStage, slot: str) -> None:
    delta = PobEquipmentDelta(
        slot=slot,
        candidate_id=503,
        candidate_name="Inferior Wand",
        dps_delta=-15.0,
    )
    rec = evaluate_fubgun_weapon_policy(delta, stage=stage)
    assert rec.verdict == Verdict.REJECT


# =============================================================================
# 6. DUAL-RING PLACEMENT MATRIX (EMPTY SLOTS & PARETO DOMINANCE)
# =============================================================================

@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
def test_dummy_dual_ring_empty_slot_recommends_empty_slot(stage: BuildProgressionStage) -> None:
    d1 = PobEquipmentDelta(
        slot="Ring 1",
        candidate_id=601,
        candidate_name="New Ring",
        current_item_name="Existing Ring 1",
        life_delta=10,
        fire_res_delta=15,
    )
    d2 = PobEquipmentDelta(
        slot="Ring 2",
        candidate_id=601,
        candidate_name="New Ring",
        current_item_name=None,
        life_delta=35,
        fire_res_delta=30,
    )
    # Ring 2 is empty -> should recommend Ring 2
    rec = evaluate_dual_ring_policy(d1, d2, stage=stage, empty_slot2=True)
    assert rec.recommended_slot == "Ring 2"
    assert "empty" in rec.summary_verdict.lower()


@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
def test_dummy_dual_ring_empty_slot_rejected_never_overwritten_by_pareto(stage: BuildProgressionStage) -> None:
    # Item is bad (e.g. causes big negative stat on empty slot)
    d1 = PobEquipmentDelta(
        slot="Ring 1",
        candidate_id=602,
        candidate_name="Bad Ring",
        current_item_name="Existing Ring 1",
        life_delta=5,
    )
    d2 = PobEquipmentDelta(
        slot="Ring 2",
        candidate_id=602,
        candidate_name="Bad Ring",
        current_item_name=None,
        life_delta=-50,
    )
    rec = evaluate_dual_ring_policy(d1, d2, stage=stage, empty_slot2=True)
    # Rejection of empty slot must NEVER recommend replacing equipped Ring 1 via Pareto
    assert rec.recommended_slot is None
    assert "neither" in rec.summary_verdict.lower()


@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
def test_dummy_dual_ring_pareto_dominance(stage: BuildProgressionStage) -> None:
    # Both slots filled, Ring 2 replacement is strictly superior to Ring 1 replacement
    d1 = PobEquipmentDelta(
        slot="Ring 1",
        candidate_id=603,
        candidate_name="Top Tier Ring",
        current_item_name="Decent Ring 1",
        life_delta=10,
        fire_res_delta=10,
    )
    d2 = PobEquipmentDelta(
        slot="Ring 2",
        candidate_id=603,
        candidate_name="Top Tier Ring",
        current_item_name="Garbage Ring 2",
        life_delta=45,
        fire_res_delta=35,
    )
    rec = evaluate_dual_ring_policy(d1, d2, stage=stage)
    assert rec.recommended_slot == "Ring 2"
    assert "dominates" in rec.summary_verdict.lower() or "ring 2" in rec.summary_verdict.lower()


# =============================================================================
# 7. DUAL-WEAPON PLACEMENT MATRIX
# =============================================================================

@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
def test_dummy_dual_weapon_empty_offhand_equips_in_empty_slot(stage: BuildProgressionStage) -> None:
    d1 = PobEquipmentDelta(
        slot="Weapon 1",
        candidate_id=701,
        candidate_name="Offhand Shield",
        current_item_name="Main Hand Wand",
        dps_delta=-10.0,
    )
    d2 = PobEquipmentDelta(
        slot="Weapon 2",
        candidate_id=701,
        candidate_name="Offhand Shield",
        current_item_name=None,
        life_delta=40,
        armour_delta=150,
        ehp_delta=15.0,
    )
    rec = evaluate_dual_weapon_policy(d1, d2, stage=stage, empty_slot2=True)
    assert rec.recommended_slot == "Weapon 2"


# =============================================================================
# 8. BUILD BREAKER MECHANICS ACROSS PROGRESSION STAGES
# =============================================================================

FLAT_FIRE_RING = """Item Class: Rings
Rarity: Rare
Firestarter Loop
Iron Ring
--------
Requirements:
Level: 20
--------
Adds 8 to 16 Fire Damage to Attacks
+40 to maximum Life
+25% to Cold Resistance
"""

FLAT_FIRE_CROSSBOW_SET2 = """Item Class: Crossbows
Rarity: Rare
Pyre Launcher
Bombard Crossbow
--------
Physical Damage: 40-90
--------
Requirements:
Level: 52
--------
Adds 15 to 30 Fire Damage to Attacks
"""

FLAT_FIRE_STAFF_SET1 = """Item Class: Two Hand Staves
Rarity: Rare
Solar Pillar
Chiming Staff
--------
Physical Damage: 50-100
--------
Requirements:
Level: 52
--------
Adds 20 to 40 Fire Damage to Attacks
75% increased Fire Damage
"""

PRE_SWAP_STAGES = [
    BuildProgressionStage.LEVELING_1_14,
    BuildProgressionStage.LEVELING_15_32,
    BuildProgressionStage.LEVELING_33_51,
]

POST_SWAP_STAGES = [
    BuildProgressionStage.SWAP_52,
    BuildProgressionStage.LEVELING_53_68,
    BuildProgressionStage.LEVEL_85,
    BuildProgressionStage.EARLY_ENDGAME,
    BuildProgressionStage.ENDGAME,
    BuildProgressionStage.MAGEBLOOD,
    BuildProgressionStage.DOT_CAP,
]


@pytest.mark.parametrize("stage", PRE_SWAP_STAGES)
def test_dummy_flat_fire_on_attack_is_safe_pre_swap(stage: BuildProgressionStage) -> None:
    ring = parse_item_text(FLAT_FIRE_RING, target_slot=SlotType.RING_1)
    ev = evaluate_candidate_build_safety(
        candidate=ring,
        slot=SlotType.RING_1,
        stage=stage,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_SAFE


@pytest.mark.parametrize("stage", POST_SWAP_STAGES)
def test_dummy_flat_fire_on_attack_is_build_breaker_post_swap(stage: BuildProgressionStage) -> None:
    ring = parse_item_text(FLAT_FIRE_RING, target_slot=SlotType.RING_1)
    ev = evaluate_candidate_build_safety(
        candidate=ring,
        slot=SlotType.RING_1,
        stage=stage,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER
    assert ev.severity == RuleSeverity.BUILD_BREAKER
    assert "ignite" in ev.reason.lower() or "oil grenade" in ev.reason.lower()


@pytest.mark.parametrize("stage", POST_SWAP_STAGES)
def test_dummy_flat_fire_on_weapon_set_2_crossbow_is_build_breaker(stage: BuildProgressionStage) -> None:
    crossbow = parse_item_text(
        FLAT_FIRE_CROSSBOW_SET2,
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


@pytest.mark.parametrize("stage", ALL_PROGRESSION_STAGES)
def test_dummy_staff_in_weapon_set_1_is_exempt_from_fire_breaker(stage: BuildProgressionStage) -> None:
    staff = parse_item_text(
        FLAT_FIRE_STAFF_SET1,
        target_slot=SlotType.MAIN_HAND,
        target_weapon_set=WeaponSetContext.WEAPON_SET_1,
    )
    ev = evaluate_candidate_build_safety(
        candidate=staff,
        slot=SlotType.MAIN_HAND,
        weapon_set=WeaponSetContext.WEAPON_SET_1,
        stage=stage,
    )
    assert ev.certainty == BuildBreakerCertainty.VERIFIED_SAFE


# =============================================================================
# 9. STAGE-AWARE NON-MATERIAL MODIFIERS & REQUIREMENT CASCADES
# =============================================================================

from companion.equipment.fubgun_priorities import is_fubgun_non_material_modifier
from companion.equipment.requirements import (
    GemRequirement,
    validate_requirement_cascades,
)
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.baseline import CharacterStatBaseline


@pytest.mark.parametrize("stage", [
    BuildProgressionStage.LEVELING_1_14,
    BuildProgressionStage.LEVELING_15_32,
    BuildProgressionStage.LEVELING_33_51,
    BuildProgressionStage.LEVELING_53_68,
])
def test_dummy_non_material_modifier_safe_in_campaign(stage: BuildProgressionStage) -> None:
    # Stun/block recovery or light radius is non-material during campaign
    assert is_fubgun_non_material_modifier("14% increased Stun and Block Recovery", stage=stage) is True
    assert is_fubgun_non_material_modifier("+15 to Light Radius", stage=stage) is True


@pytest.mark.parametrize("stage", [
    BuildProgressionStage.EARLY_ENDGAME,
    BuildProgressionStage.ENDGAME,
    BuildProgressionStage.MAGEBLOOD,
    BuildProgressionStage.DOT_CAP,
])
def test_dummy_non_material_modifier_strict_in_endgame(stage: BuildProgressionStage) -> None:
    # In endgame, unmodeled affixes are NOT treated as non-material; safety/precedence remains conservative
    assert is_fubgun_non_material_modifier("14% increased Stun and Block Recovery", stage=stage) is False


def test_dummy_unmet_attribute_requirement_triggers_cascade_failure() -> None:
    loadout = EquippedLoadout(loadout_id="dummy_loadout", character_id="dummy_char", revision=1)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="dummy_char",
        anchored_loadout_revision=1,
        strength=40,
    )
    # Item requires 110 Strength, character only has 40
    item_text = """Item Class: Body Armours
Rarity: Rare
Colossus Plate
Astral Plate
--------
Requirements:
Level: 50
Str: 110
--------
+80 to maximum Life
+35% to Fire Resistance
"""
    candidate = parse_item_text(item_text, target_slot=SlotType.BODY_ARMOUR)
    res = validate_requirement_cascades(
        loadout=loadout,
        candidate=candidate,
        slot=SlotType.BODY_ARMOUR,
        baseline=baseline,
    )
    assert res.is_satisfied is False
    assert any(d.attribute == "str" and d.target_type == "candidate" for d in res.candidate_deficiencies)


def test_dummy_requirement_cascade_fails_when_gem_loses_attributes() -> None:
    loadout = EquippedLoadout(loadout_id="dummy_loadout", character_id="dummy_char", revision=1)
    # Character currently has 60 Strength (25 base + 35 from equipped amulet)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="dummy_char",
        anchored_loadout_revision=1,
        strength=60,
    )
    # Current amulet gives +35 Strength
    current_amulet_text = """Item Class: Amulets
Rarity: Rare
Brawn Choker
Coral Amulet
--------
+35 to Strength
+40 to maximum Life
"""
    current_amulet = parse_item_text(current_amulet_text, target_slot=SlotType.AMULET)
    loadout.set_slot(SlotType.AMULET, current_amulet)

    # Candidate amulet gives NO strength
    candidate_amulet_text = """Item Class: Amulets
Rarity: Rare
Pure Fire Amulet
Coral Amulet
--------
+30% to Fire Resistance
+40 to maximum Life
"""
    candidate = parse_item_text(candidate_amulet_text, target_slot=SlotType.AMULET)

    # Critical gem requires 50 Strength. Replacing amulet drops strength to 60 - 35 = 25 < 50!
    critical_gems = [
        GemRequirement(gem_name="Steelskin", strength=50, is_critical=True)
    ]

    res = validate_requirement_cascades(
        loadout=loadout,
        candidate=candidate,
        slot=SlotType.AMULET,
        baseline=baseline,
        critical_gems=critical_gems,
    )
    assert res.is_satisfied is False
    assert any(d.target_type == "gem" and d.target_name == "Steelskin" for d in res.gem_cascading_deficiencies)

