"""Unit tests for Decisive & Bold Equipment Advisor (TDD RED).

Validates that the companion makes clear, decisive recommendations without sitting
on the fence (no 'ngawang' advice):
1. Net Downgrade Rejection: If an item drops EHP, Life, Armour, and DPS just for a minor
   resistance bump (like Gloom Grip vs Ghoul Talons), it MUST be evaluated as `REJECT / KEEP CURRENT`.
2. Dangerous Resistance Loss: In LEVELING_15_32, trading away significant resistances (<= -6%)
   and heavy defense (Armour/Evasion <= -40) for a small life gain (<= 25) must be decisively flagged.
3. Legitimate Trade-offs: Substantial resistance shifts with healthy EHP (e.g. +40 Fire for -30 Cold)
   remain CONDITIONAL_UPGRADE.
4. Pure upgrades remain EQUIP_NOW.
"""

from __future__ import annotations

import pytest

from companion.equipment.fubgun_priorities import (
    evaluate_fubgun_equipment_policy,
    evaluate_fubgun_helmet_policy,
    evaluate_fubgun_weapon_policy,
)
from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
from companion.equipment.precedence import Verdict
from companion.equipment.rules import BuildProgressionStage


def test_gloom_grip_vs_ghoul_talons_is_decisively_rejected_as_net_downgrade():
    """Gloom Grip loses Life (-13), Armour (-12), EHP (-5.40), and DPS (-0.67) for +8% Lightning.

    The advisor must NOT say CONDITIONAL_UPGRADE. It must decisively output REJECT.
    """
    delta = PobEquipmentDelta(
        slot="Gloves",
        candidate_id=901,
        candidate_name="Gloom Grip",
        current_item_name="Ghoul Talons",
        life_delta=-13,
        lightning_res_delta=8,
        armour_delta=-12,
        evasion_delta=0,
        es_delta=0,
        ehp_delta=-5.40,
        dps_delta=-0.67,
    )

    rec = evaluate_fubgun_equipment_policy(
        delta,
        stage=BuildProgressionStage.LEVELING_15_32,
        use_color=False,
    )

    assert rec.verdict == Verdict.REJECT
    assert "Net downgrade" in rec.reason
    assert "Keep current item" in rec.reason
    assert "🔴 REJECT / KEEP CURRENT" in rec.formatted_output


def test_helmet_net_downgrade_is_decisively_rejected():
    """Helmet candidate that drops Life, EHP, Armour, and DPS for +10% Cold Res must be REJECTed."""
    delta = PobEquipmentDelta(
        slot="Helmet",
        candidate_id=902,
        candidate_name="Inferior Cap",
        current_item_name="Skull Ward",
        life_delta=-15,
        cold_res_delta=10,
        armour_delta=-30,
        evasion_delta=-20,
        es_delta=0,
        ehp_delta=-8.20,
        dps_delta=-0.50,
    )

    rec = evaluate_fubgun_helmet_policy(
        delta,
        stage=BuildProgressionStage.LEVELING_15_32,
        use_color=False,
    )

    assert rec.verdict == Verdict.REJECT
    assert "Net downgrade" in rec.reason
    assert "Keep current item" in rec.reason
    assert "🔴 REJECT / KEEP CURRENT" in rec.formatted_output


def test_legitimate_resistance_shift_remains_conditional_upgrade():
    """Shifting resistances (+40 Fire for -30 Cold) with positive/neutral EHP remains CONDITIONAL_UPGRADE."""
    delta = PobEquipmentDelta(
        slot="Gloves",
        candidate_id=903,
        candidate_name="Fire Heavy Gloves",
        current_item_name="Cold Heavy Gloves",
        fire_res_delta=40,
        cold_res_delta=-30,
        life_delta=0,
        ehp_delta=2.0,
        dps_delta=0.0,
    )

    rec = evaluate_fubgun_equipment_policy(
        delta,
        stage=BuildProgressionStage.LEVELING_15_32,
        use_color=False,
    )

    assert rec.verdict == Verdict.CONDITIONAL_UPGRADE


def test_glyph_pelt_vs_maelstrom_keep_remains_equip_now():
    """Glyph Pelt (+15% Fire, +4% Lightning, +7 Life, +17.29 EHP, -82 Armour) is EQUIP_NOW."""
    delta = PobEquipmentDelta(
        slot="Body Armour",
        candidate_id=904,
        candidate_name="Glyph Pelt",
        current_item_name="Maelström Keep",
        life_delta=7,
        fire_res_delta=15,
        lightning_res_delta=4,
        armour_delta=-82,
        ehp_delta=17.29,
        dps_delta=0.0,
    )

    rec = evaluate_fubgun_equipment_policy(
        delta,
        stage=BuildProgressionStage.LEVELING_15_32,
        use_color=False,
    )

    assert rec.verdict == Verdict.EQUIP_NOW
    assert "🟢 EQUIP NOW" in rec.formatted_output


def test_maelstrom_keep_vs_glyph_pelt_is_decisively_rejected_due_to_heavy_res_and_ehp_loss():
    """Maelström Keep (+82 Armour, -7 Life, -15% Fire, -4% Lightning, -16.80 EHP) must be REJECTed.

    The advisor must NOT say CONDITIONAL_UPGRADE for a secondary local armor gain
    when it causes severe resistance regression (-19% total) and drops Total EHP.
    """
    delta = PobEquipmentDelta(
        slot="Body Armour",
        candidate_id=905,
        candidate_name="Maelström Keep",
        current_item_name="Glyph Pelt",
        life_delta=-7,
        fire_res_delta=-15,
        lightning_res_delta=-4,
        armour_delta=82,
        evasion_delta=0,
        es_delta=0,
        ehp_delta=-16.80,
        dps_delta=0.0,
    )

    rec = evaluate_fubgun_equipment_policy(
        delta,
        stage=BuildProgressionStage.LEVELING_15_32,
        use_color=False,
    )

    assert rec.verdict == Verdict.REJECT
    assert "Net downgrade" in rec.reason or "resistance" in rec.reason.lower()
    assert "🔴 REJECT / KEEP CURRENT" in rec.formatted_output


def test_kraken_dome_vs_skull_ward_is_decisively_rejected_as_defense_compromise():
    """Kraken Dome (+20 Life, +9.51 EHP, -7% Fire, -2% Lightning, -107 Armour) must be REJECTed.

    The advisor must NOT say CONDITIONAL_UPGRADE for a level 6 helm that strips -9% resistances
    and collapses local armor/evasion (-107 Armour) for a minor flat life gain of +20.
    """
    delta = PobEquipmentDelta(
        slot="Helmet",
        candidate_id=906,
        candidate_name="Kraken Dome",
        current_item_name="Skull Ward",
        life_delta=20,
        fire_res_delta=-7,
        lightning_res_delta=-2,
        armour_delta=-107,
        evasion_delta=0,
        es_delta=0,
        ehp_delta=9.51,
        dps_delta=-0.15,
    )

    rec = evaluate_fubgun_helmet_policy(
        delta,
        stage=BuildProgressionStage.LEVELING_15_32,
        use_color=False,
    )

    assert rec.verdict == Verdict.REJECT
    assert "🔴 REJECT / KEEP CURRENT" in rec.formatted_output


def test_shades_lunar_amulet_vs_gale_medallion_is_decisively_rejected_as_net_downgrade():
    """Shade's Lunar Amulet (+23 ES, +4.45 EHP, -6 Life, -0.93 DPS, no resistances) must be REJECTed.

    The advisor must NOT say CONDITIONAL_UPGRADE for an amulet that loses DPS and Life
    with zero resistance gain, just because it has a tiny +23 Energy Shield secondary gain.
    """
    delta = PobEquipmentDelta(
        slot="Amulet",
        candidate_id=907,
        candidate_name="Shade's Lunar Amulet of the Mongoose",
        current_item_name="Gale Medallion",
        life_delta=-6,
        dps_delta=-0.93,
        es_delta=23,
        ehp_delta=4.45,
        fire_res_delta=0,
        cold_res_delta=0,
        lightning_res_delta=0,
        chaos_res_delta=0,
    )

    rec = evaluate_fubgun_equipment_policy(
        delta,
        stage=BuildProgressionStage.LEVELING_15_32,
        use_color=False,
    )

    assert rec.verdict == Verdict.REJECT
    assert "🔴 REJECT / KEEP CURRENT" in rec.formatted_output


def test_horror_grip_vs_ghoul_talons_is_decisively_rejected_due_to_flat_damage_and_life_loss():
    """Horror Grip (+18% Fire Res, +16 Armour, +10.72 EHP) drops DPS (-2.85) and Life (-3).

    For Fubgun campaign/leveling, Gloves/Rings are primary offensive flat attack damage sources.
    Dropping DPS and Life for a modest single resistance must be decisively REJECTED,
    boldly declaring that Ghoul Talons is better.
    """
    delta = PobEquipmentDelta(
        slot="Gloves",
        candidate_id=909,
        candidate_name="Horror Grip",
        current_item_name="Ghoul Talons",
        life_delta=-3,
        fire_res_delta=18,
        armour_delta=16,
        evasion_delta=-23,
        ehp_delta=10.72,
        dps_delta=-2.85,
    )

    rec = evaluate_fubgun_equipment_policy(
        delta,
        stage=BuildProgressionStage.LEVELING_15_32,
        use_color=False,
    )

    assert rec.verdict == Verdict.REJECT
    assert "Ghoul Talons LEBIH BAGUS" in rec.reason or "Keep current item" in rec.reason
    assert "flat damage" in rec.reason.lower() or "dps" in rec.reason.lower()
    assert "🔴 REJECT / KEEP CURRENT" in rec.formatted_output


def test_carrion_core_vs_fate_core_is_decisively_equipped_as_massive_weapon_dps_upgrade():
    """Carrion Core (+16.39 DPS, -19 Life, -15.25 EHP) vs Fate Core.

    In Fubgun campaign leveling, weapons are the primary damage engine.
    A massive DPS upgrade (+16.39 DPS) with zero resistance loss and only minor
    incidental life loss from attributes (-19 Life) must be decisively EQUIP_NOW.
    """
    delta = PobEquipmentDelta(
        slot="Weapon 1",
        candidate_id=910,
        candidate_name="Carrion Core",
        current_item_name="Fate Core",
        dps_delta=16.39,
        life_delta=-19,
        ehp_delta=-15.25,
    )
    rec = evaluate_fubgun_weapon_policy(
        delta,
        stage=BuildProgressionStage.LEVELING_15_32,
        use_color=False,
    )
    assert rec.verdict == Verdict.EQUIP_NOW
    assert "Carrion Core LEBIH BAGUS" in rec.reason or "DPS upgrade" in rec.reason
    assert "🟢 EQUIP NOW" in rec.formatted_output


def test_maelstrom_paw_vs_ghoul_talons_policy_downgrades_to_conditional_upgrade():
    """Maelström Paw vs Ghoul Talons on Gloves base policy.

    Maelström Paw gives +7 Life, +8% Lightning Res, but loses -13.19 DPS.
    In base fubgun equipment policy, material DPS loss on offensive slot
    downgrades the primary defensive gain to CONDITIONAL_UPGRADE.
    """
    delta = PobEquipmentDelta(
        slot="Gloves",
        candidate_id=911,
        candidate_name="Maelström Paw",
        current_item_name="Ghoul Talons",
        dps_delta=-13.19,
        life_delta=7,
        lightning_res_delta=8,
        armour_delta=-37,
        evasion_delta=-31,
        es_delta=25,
        ehp_delta=22.84,
    )
    rec = evaluate_fubgun_equipment_policy(
        delta,
        stage=BuildProgressionStage.LEVELING_15_32,
        use_color=False,
    )
    assert rec.verdict == Verdict.CONDITIONAL_UPGRADE
    assert "Trade-off between Life/Resistance upgrade and offensive damage loss" in rec.reason






