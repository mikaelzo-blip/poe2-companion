"""Unit tests for Decisive & Zone-Aware Tactical Advisor (TDD RED)."""

from __future__ import annotations

import pytest

from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
from companion.equipment.tactical_advisor import (
    TacticalAdvice,
    Verdict,
    generate_tactical_advice,
)


def test_tactical_advice_maelstrom_keep_in_g2_1_is_boldly_rejected_with_zone_and_sustain_context():
    """Maelström Keep in G2_1:

    - Net EHP loss (-16.80) and Fire Res loss (-15%) in Act 2 Vastiri is rejected.
    - Mentions lethal fire threat in Vastiri Outskirts / Caravan.
    - Mentions sustain value of 5.8 Life Regen per second for stash/farming.
    - Mentions warning about losing +12 Strength.
    """
    delta = PobEquipmentDelta(
        slot="Body Armour",
        candidate_id=101,
        candidate_name="Maelström Keep",
        current_item_name="Glyph Pelt",
        life_delta=-7,
        fire_res_delta=-15,
        lightning_res_delta=-4,
        armour_delta=82,
        ehp_delta=-16.80,
        dps_delta=0.0,
    )

    candidate_text = """Item Class: Body Armours
Rarity: Rare
Maelström Keep
Shrouded Vest
Evasion Rating: 209 (augmented)
Requirements:
Level: 16
Dex: 28
Sockets: S
Item Level: 19
+11 to Evasion Rating
50% increased Evasion Rating
+26 to maximum Life
+10% to Lightning Resistance
5.8 Life Regeneration per second
"""

    current_item_text = """Item Class: Body Armours
Rarity: Rare
Glyph Pelt
Iron Cuirass
Armour: 127 (augmented)
Requirements:
Level: 11
Str: 21
Item Level: 14
10% increased Armour
+9 to maximum Life
+12 to Strength
+15% to Fire Resistance
+14% to Lightning Resistance
1 to 4 Physical Thorns damage
"""

    advice: TacticalAdvice = generate_tactical_advice(
        delta=delta,
        candidate_raw=candidate_text,
        current_raw=current_item_text,
        zone_id="G2_1",
        character_level=19,
    )

    assert advice.verdict == Verdict.REJECT
    assert "🛑" in advice.verdict_badge or "TAHAN" in advice.verdict_badge
    assert "Vastiri" in advice.zone_name or "G2_1" in advice.zone_name
    assert "Fire" in advice.zone_threat_warning
    assert "5.8" in advice.sustain_evaluation or "Regen" in advice.sustain_evaluation
    assert "Strength" in advice.attribute_warning or "12" in advice.attribute_warning
    assert "Stash" in advice.actionable_recommendation or "simpan" in advice.actionable_recommendation.lower()



def test_tactical_advice_kraken_dome_in_g2_1_is_boldly_rejected_with_lethal_fire_warning():
    """Kraken Dome in G2_1:
    - Drops -7% Fire Res in Act 2 Vastiri (is_lethal_drop == True).
    - Drops -107 Armour.
    - Only gains +20 Life and +9.51 EHP.
    Tactical advisor MUST decisively REJECT with badge '🛑 TAHAN GEAR LAMA',
    explicitly explaining that +20 Life does not justify losing lethal Fire Resistance
    and collapsing base defenses in Act 2 Vastiri.
    """
    delta = PobEquipmentDelta(
        slot="Helmet",
        candidate_id=103,
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
    advice = generate_tactical_advice(
        delta=delta,
        candidate_raw="Item Class: Helmets\nRarity: Rare\nKraken Dome\nRusted Greathelm\nArmour: 32\n+20 to maximum Life\n2.7 Life Regeneration per second\n",
        current_raw="Item Class: Helmets\nRarity: Rare\nSkull Ward\nVisored Helm\nArmour: 75\nEvasion Rating: 64\n+7% to Fire Resistance\n+9% to Lightning Resistance\n",
        zone_id="G2_1",
        character_level=19,
    )
    assert advice.verdict == Verdict.REJECT
    assert "🛑" in advice.verdict_badge or "TAHAN" in advice.verdict_badge
    assert "Vastiri" in advice.zone_name or "G2_1" in advice.zone_name
    assert "Fire" in advice.zone_threat_warning
    assert "Tetap gunakan Skull Ward" in advice.actionable_recommendation or "Skull Ward" in advice.actionable_recommendation









def test_tactical_advice_with_character_stat_unmet_attribute_requirement():
    """Candidate requires 60 Strength, but character currently only has 48 Strength."""
    delta = PobEquipmentDelta(
        slot="Body Armour",
        candidate_id=103,
        candidate_name="Colossus Mail",
        current_item_name="Glyph Pelt",
        life_delta=30,
        fire_res_delta=10,
        lightning_res_delta=10,
        armour_delta=150,
        ehp_delta=40.0,
        dps_delta=0.0,
    )
    cand_raw = (
        "Item Class: Body Armours\n"
        "Rarity: Rare\n"
        "Colossus Mail\n"
        "Armour: 250\n"
        "Requirements:\n"
        "Level: 36\n"
        "Str: 60\n"
        "+30 to maximum Life\n"
        "+10% to Fire Resistance\n"
        "+10% to Lightning Resistance\n"
    )
    char_stats = {
        "strength": 48,
        "dexterity": 85,
        "intelligence": 53,
        "level": 37,
        "fire_res": 23,
        "cold_res": -3,
        "lightning_res": -4,
        "chaos_res": 0,
        "life": 723,
    }
    advice = generate_tactical_advice(
        delta=delta,
        candidate_raw=cand_raw,
        zone_id="G2_1",
        character_level=37,
        character_stats=char_stats,
    )
    # Even though stats are positive, unmet attribute requirement prevents direct EQUIP_NOW
    assert advice.verdict in (Verdict.CONDITIONAL_UPGRADE, Verdict.REJECT)
    assert "Strength" in advice.attribute_warning or any("Strength" in b for b in advice.trade_off_bullets)
    assert "48" in advice.attribute_warning or "60" in advice.attribute_warning or any("60" in b for b in advice.trade_off_bullets)


def test_tactical_advice_with_character_stat_negative_cold_resistance_veto():
    """Character has -3% Cold Res; losing another -5% Cold Res is lethal and must be rejected."""
    delta = PobEquipmentDelta(
        slot="Ring",
        candidate_id=104,
        candidate_name="Pyre Loop",
        current_item_name="Frost Loop",
        cold_res_delta=-5,
        fire_res_delta=15,
        life_delta=10,
        ehp_delta=5.0,
        dps_delta=2.0,
    )
    char_stats = {
        "strength": 48,
        "dexterity": 85,
        "intelligence": 53,
        "level": 37,
        "fire_res": 23,
        "cold_res": -3,
        "lightning_res": -4,
        "chaos_res": 0,
        "life": 723,
    }
    advice = generate_tactical_advice(
        delta=delta,
        candidate_raw="Item Class: Rings\nRarity: Rare\nPyre Loop\n+15% to Fire Resistance\n+10 to maximum Life\n",
        zone_id="G2_1",
        character_level=37,
        character_stats=char_stats,
    )
    assert advice.verdict == Verdict.REJECT
    assert "Cold" in advice.tactical_headline or "Cold" in advice.zone_threat_warning or any("Cold" in b for b in advice.trade_off_bullets)
    assert "-3" in advice.tactical_headline or "-3" in advice.zone_threat_warning or any("-3" in b for b in advice.trade_off_bullets)


def _clean_upgrade_delta():
    return PobEquipmentDelta(
        slot="Helmet", candidate_id=102, candidate_name="Superior Visor", current_item_name="Old Cap",
        life_delta=25, fire_res_delta=15, lightning_res_delta=10, armour_delta=40, ehp_delta=32.0, dps_delta=1.5,
    )


def test_tactical_never_promotes():
    adv = generate_tactical_advice(_clean_upgrade_delta(), zone_id="G1_1", base_verdict="CONDITIONAL_UPGRADE")
    assert adv.verdict == Verdict.CONDITIONAL_UPGRADE


def test_tactical_defaults_to_conditional_base():
    adv = generate_tactical_advice(_clean_upgrade_delta(), zone_id="G1_1")
    assert adv.verdict == Verdict.CONDITIONAL_UPGRADE


def test_tactical_keeps_equip_now_base_without_veto():
    adv = generate_tactical_advice(_clean_upgrade_delta(), zone_id="G2_1", base_verdict="EQUIP_NOW")
    assert adv.verdict == Verdict.EQUIP_NOW
    assert "GANTI" in adv.verdict_badge


def test_tactical_vetoes_lethal_zone_drop():
    delta = PobEquipmentDelta(
        slot="Helmet", candidate_id=103, candidate_name="Kraken Dome", current_item_name="Skull Ward",
        life_delta=20, fire_res_delta=-7, lightning_res_delta=-2, armour_delta=-107, ehp_delta=9.51, dps_delta=-0.15,
    )
    adv = generate_tactical_advice(delta, zone_id="G2_1", character_level=19, base_verdict="EQUIP_NOW")
    assert adv.verdict == Verdict.REJECT


def test_tactical_does_not_veto_dps_loss_outside_zone_rule():
    delta = PobEquipmentDelta(
        slot="Weapon 1", candidate_id=201, candidate_name="Rusty Crossbow", current_item_name="Siege Crossbow",
        dps_delta=-5.4, life_delta=0,
    )
    adv = generate_tactical_advice(delta, zone_id="G2_1", character_level=19, base_verdict="CONDITIONAL_UPGRADE")
    assert adv.verdict == Verdict.CONDITIONAL_UPGRADE


@pytest.mark.parametrize("verdict", ["EQUIP_NOW", "CONDITIONAL_UPGRADE", "REJECT", "INSUFFICIENT_DATA"])
def test_tactical_text_has_no_fubgun(verdict):
    adv = generate_tactical_advice(_clean_upgrade_delta(), base_verdict=verdict)
    text = adv.model_dump_json().lower()
    assert "fubgun" not in text and "granat" not in text and "grenade" not in text
