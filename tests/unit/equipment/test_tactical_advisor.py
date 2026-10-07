"""Unit tests for Decisive & Zone-Aware Tactical Advisor (TDD RED)."""

from __future__ import annotations

import pytest

from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
from companion.equipment.precedence import Verdict
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.tactical_advisor import (
    TacticalAdvice,
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


def test_tactical_advice_clean_upgrade_is_boldly_equipped():
    """A clean upgrade without dangerous resistance drops gets bold EQUIP recommendation."""
    delta = PobEquipmentDelta(
        slot="Helmet",
        candidate_id=102,
        candidate_name="Superior Visor",
        current_item_name="Old Cap",
        life_delta=25,
        fire_res_delta=15,
        lightning_res_delta=10,
        armour_delta=40,
        ehp_delta=32.0,
        dps_delta=1.5,
    )

    advice = generate_tactical_advice(
        delta=delta,
        candidate_raw="Item Class: Helmets\nRarity: Rare\nSuperior Visor\n+25 to maximum Life\n+15% to Fire Resistance\n",
        zone_id="G2_1",
        character_level=19,
    )

    assert advice.verdict == Verdict.EQUIP_NOW
    assert "🟢" in advice.verdict_badge or "GANTI" in advice.verdict_badge
    assert "aman" in advice.actionable_recommendation.lower() or "pasang" in advice.actionable_recommendation.lower()


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


def test_tactical_advice_weapon_dps_loss_is_decisively_rejected():
    """Any candidate weapon that drops DPS on current setup must be decisively REJECTed."""
    delta = PobEquipmentDelta(
        slot="Weapon 1",
        candidate_id=201,
        candidate_name="Rusty Crossbow",
        current_item_name="Siege Crossbow",
        dps_delta=-5.4,
        life_delta=0,
    )
    advice = generate_tactical_advice(
        delta=delta,
        candidate_raw="Item Class: Crossbows\nRarity: Magic\nRusty Crossbow\nPhysical Damage: 12-25\n",
        current_raw="Item Class: Crossbows\nRarity: Rare\nSiege Crossbow\nPhysical Damage: 30-65\n",
        zone_id="G2_1",
        character_level=19,
    )
    assert advice.verdict == Verdict.REJECT
    assert "senjata" in advice.tactical_headline.lower()
    assert "DPS" in advice.tactical_headline


def test_tactical_advice_boots_movement_speed_loss_is_decisively_rejected():
    """Candidate boots dropping >= 10% movement speed without massive defense must be REJECTed."""
    delta = PobEquipmentDelta(
        slot="Boots",
        candidate_id=202,
        candidate_name="Heavy Iron Sabatons",
        current_item_name="Runner Boots",
        movement_speed_delta=-15.0,
        life_delta=10,
        fire_res_delta=5,
    )
    advice = generate_tactical_advice(
        delta=delta,
        candidate_raw="Item Class: Boots\nRarity: Rare\nHeavy Iron Sabatons\nArmour: 50\n+10 to maximum Life\n+5% to Fire Resistance\n",
        current_raw="Item Class: Boots\nRarity: Magic\nRunner Boots\nEvasion Rating: 40\n15% increased Movement Speed\n",
        zone_id="G2_1",
        character_level=19,
    )
    assert advice.verdict == Verdict.REJECT
    assert "sepatu" in advice.tactical_headline.lower() or "movement speed" in advice.tactical_headline.lower()


def test_tactical_advice_shades_amulet_with_attribute_drain_and_dps_loss_is_decisively_rejected():
    """Shade's Lunar Amulet vs Gale Medallion:
    - Causes -13 Dexterity, -3 Strength, -3 Intelligence.
    - Drops -0.93 DPS and -6 Life.
    - Only gains +23 ES and +4.45 EHP.
    Tactical advisor MUST decisively REJECT with badge '🛑 TAHAN GEAR LAMA',
    warning about attribute drain and net downgrade.
    """
    delta = PobEquipmentDelta(
        slot="Amulet",
        candidate_id=908,
        candidate_name="Shade's Lunar Amulet of the Mongoose",
        current_item_name="Gale Medallion",
        life_delta=-6,
        dps_delta=-0.93,
        es_delta=23,
        ehp_delta=4.45,
    )
    advice = generate_tactical_advice(
        delta=delta,
        candidate_raw="Item Class: Amulets\nRarity: Magic\nShade's Lunar Amulet of the Mongoose\nLunar Amulet\n+23 to maximum Energy Shield\n11% increased Evasion Rating\n",
        current_raw="Item Class: Amulets\nRarity: Rare\nGale Medallion\nJade Amulet\n+10 to Dexterity\n+3 to all Attributes\n+1 to Level of all Projectile Skills\n13% increased Critical Damage Bonus\n12% increased maximum Energy Shield\n",
        zone_id="G2_1",
        character_level=19,
    )
    assert advice.verdict == Verdict.REJECT
    assert "🛑" in advice.verdict_badge or "TAHAN" in advice.verdict_badge
    assert "amulet" in advice.tactical_headline.lower() or "kalung" in advice.tactical_headline.lower()
    assert "atribut" in advice.attribute_warning.lower() or "dexterity" in advice.attribute_warning.lower()


def test_tactical_advice_horror_grip_vs_ghoul_talons_decisively_rejected():
    """Horror Grip vs Ghoul Talons in G2_1:
    - Drops DPS (-2.85) and Life (-3).
    - Gains +18% Fire Res and +16 Armour.
    Tactical advisor MUST decisively output REJECT ('🛑 TAHAN GEAR LAMA'),
    declaring that Ghoul Talons is better for the grenade build.
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
    advice = generate_tactical_advice(
        delta=delta,
        candidate_raw="Item Class: Gloves\nRarity: Rare\nHorror Grip\nStocky Mitts\nArmour: 43\n+10 to maximum Life\n+18% to Fire Resistance\n",
        current_raw="Item Class: Gloves\nRarity: Rare\nGhoul Talons\nLayered Gauntlets\nArmour: 27\nEvasion Rating: 23\n+13 to maximum Life\nAdds 2 to 6 Physical Damage to Attacks\nAdds 5 to 11 Cold Damage to Attacks\n",
        zone_id="G2_1",
        character_level=19,
        stage=BuildProgressionStage.LEVELING_15_32,
    )
    assert advice.verdict == Verdict.REJECT
    assert "TAHAN GEAR LAMA" in advice.verdict_badge
    assert "sarung tangan" in advice.tactical_headline.lower() or "glove" in advice.tactical_headline.lower()
    assert "Ghoul Talons" in advice.tactical_headline or "Ghoul Talons" in advice.actionable_recommendation
    assert "lebih bagus" in advice.tactical_headline.lower() or "tahan" in advice.tactical_headline.lower()


def test_tactical_advice_maelstrom_paw_vs_ghoul_talons_decisively_rejected():
    """Maelström Paw vs Ghoul Talons on Gloves in G2_1:
    - Candidate has +19 Life, +8% Lightning Res, but loses -13.19 DPS, -7 Dex,
      and loses sustain (Life on Hit & Mana on Kill).
    Tactical advisor MUST decisively output REJECT ('🛑 TAHAN GEAR LAMA'),
    declaring that Ghoul Talons is better for the grenade build.
    """
    delta = PobEquipmentDelta(
        slot="Gloves",
        candidate_id=911,
        candidate_name="Maelström Paw",
        current_item_name="Ghoul Talons",
        life_delta=7,
        lightning_res_delta=8,
        armour_delta=-37,
        evasion_delta=-31,
        es_delta=25,
        ehp_delta=22.84,
        dps_delta=-13.19,
    )
    cand_raw = (
        "Item Class: Gloves\nRarity: Rare\nMaelström Paw\nSombre Gloves\n"
        "Energy Shield: 17\nRequires Level 16, 17 Int\n"
        "14% increased Energy Shield\n+78 to Accuracy Rating\n+19 to Maximum Life\n"
        "18% increased Critical Damage Bonus\n+8% to Lightning Resistance\n"
    )
    curr_raw = (
        "Item Class: Gloves\nRarity: Rare\nGhoul Talons\nLayered Gauntlets\n"
        "Armour: 27\nEvasion Rating: 23\nRequires Level 16, 13 Str, 13 Dex\n"
        "Adds 2 to 6 Physical Damage to Attacks\nAdds 5 to 11 Cold damage to Attacks\n"
        "+33 to maximum Life\n+7 to Dexterity\nGain 2 Life per Enemy Hit with Attacks\n"
        "Gain 4 Mana per enemy killed\n"
    )
    advice = generate_tactical_advice(
        delta=delta,
        candidate_raw=cand_raw,
        current_raw=curr_raw,
        zone_id="G2_1",
        character_level=22,
        stage=BuildProgressionStage.LEVELING_15_32,
    )
    assert advice.verdict == Verdict.REJECT
    assert "TAHAN GEAR LAMA" in advice.verdict_badge
    assert "Ghoul Talons LEBIH BAGUS" in advice.tactical_headline
    assert "Maelström Paw" in advice.tactical_headline
    assert "damage ofensif" in advice.tactical_headline.lower()


def test_tactical_advice_carrion_core_weapon_dps_gain_is_decisively_equipped():
    """Carrion Core (+16.39 DPS, -19 Life, -15.25 EHP) vs Fate Core in G2_1:
    Even with -19 Life (from losing +8 Str), the huge weapon DPS boost must make
    the tactical advisor decisively recommend EQUIP_NOW.
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
    advice = generate_tactical_advice(
        delta=delta,
        candidate_raw="Item Class: Crossbows\nRarity: Rare\nCarrion Core\nDyad Crossbow\nPhysical Damage: 17-47\n+12 to Dexterity\n",
        current_raw="Item Class: Crossbows\nRarity: Rare\nFate Core\nVarnished Crossbow\nPhysical Damage: 20-59\n+8 to Strength\n",
        zone_id="G2_1",
        character_level=20,
        stage=BuildProgressionStage.LEVELING_15_32,
    )
    assert advice.verdict == Verdict.EQUIP_NOW
    assert "GANTI SEKARANG" in advice.verdict_badge
    assert "Carrion Core LEBIH BAGUS" in advice.tactical_headline
    assert "16.39" in advice.tactical_headline


def test_tactical_advice_eagle_ward_vs_glyph_pelt_is_decisively_equipped():
    """Eagle Ward (+8 Life, +4% Fire Res, -4% Lightning Res, +18 Armour, +128 Evasion, +2 Str)
    vs Glyph Pelt in G2_1 (Vastiri Outskirts):
    Defenses increase drastically (Armour + Evasion), Life increases, Fire Res (zone threat) increases,
    and net elemental resistance is even (0%). This must be decisively EQUIP_NOW.
    Additionally, there must be NO attribute loss warning (Strength gained), and NO misleading
    'Kehilangan Fire Resistance' warning since Fire Resistance increased.
    """
    delta = PobEquipmentDelta(
        slot="Body Armour",
        candidate_id=920,
        candidate_name="Eagle Ward",
        current_item_name="Glyph Pelt",
        life_delta=8,
        fire_res_delta=4,
        lightning_res_delta=-4,
        armour_delta=18,
        evasion_delta=128,
        ehp_delta=8.0,
        strength_delta=2,
    )
    cand_raw = (
        "Item Class: Body Armours\n"
        "Rarity: Rare\n"
        "Eagle Ward\n"
        "Cloaked Mail\n"
        "Armour: 145\n"
        "Evasion Rating: 128\n"
        "Requirements:\n"
        "Level: 26\n"
        "Str: 25\n"
        "Dex: 25\n"
        "+6 to Armour\n"
        "+5 to Evasion Rating\n"
        "14% increased Armour and Evasion\n"
        "+17 to maximum Life\n"
        "+14 to Strength\n"
        "+19% to Fire Resistance\n"
        "+10% to Lightning Resistance\n"
    )
    curr_raw = (
        "Item Class: Body Armours\n"
        "Rarity: Rare\n"
        "Glyph Pelt\n"
        "Iron Cuirass\n"
        "Armour: 127\n"
        "Requirements:\n"
        "Level: 11\n"
        "Str: 21\n"
        "10% increased Armour\n"
        "+9 to maximum Life\n"
        "+12 to Strength\n"
        "+15% to Fire Resistance\n"
        "+14% to Lightning Resistance\n"
        "1 to 4 Physical Thorns damage\n"
    )
    advice = generate_tactical_advice(
        delta=delta,
        candidate_raw=cand_raw,
        current_raw=curr_raw,
        zone_id="G2_1",
        character_level=24,
        stage=BuildProgressionStage.LEVELING_15_32,
    )
    assert advice.verdict == Verdict.EQUIP_NOW
    assert "GANTI SEKARANG" in advice.verdict_badge or "PASANG" in advice.verdict_badge
    assert "Eagle Ward LEBIH BAGUS" in advice.tactical_headline
    assert advice.attribute_warning == ""
    assert "Kehilangan Fire Resistance" not in advice.zone_threat_warning


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


def test_tactical_advice_massive_life_amulet_with_minor_dps_loss_is_decisively_equipped():
    """Sorrow Noose vs Gale Medallion:
    - Gains +100 Life, +88.47 Total EHP.
    - Has +1 to Level of all Spell Skills, 15% increased Spell Damage.
    - Drops secondary attack DPS by -28.99.
    Tactical advisor MUST NOT veto/reject, but decisively output EQUIP_NOW
    for the massive survivability and spell progression boost.
    """
    delta = PobEquipmentDelta(
        slot="Amulet",
        candidate_id=999,
        candidate_name="Sorrow Noose",
        current_item_name="Gale Medallion",
        life_delta=100,
        ehp_delta=88.47,
        es_delta=-7,
        dps_delta=-28.99,
        fire_res_delta=0,
        cold_res_delta=0,
        lightning_res_delta=0,
        chaos_res_delta=0,
    )
    candidate_raw = """Item Class: Amulets
Rarity: Rare
Sorrow Noose
Jade Amulet
--------
Requirements:
Level: 36
--------
+11 to Dexterity
--------
+1 to Level of all Spell Skills
15% increased Spell Damage
+91 to maximum Life
+20 to Dexterity
10.8 Life Regeneration per second"""

    current_raw = """Item Class: Amulets
Rarity: Rare
Gale Medallion
Jade Amulet
--------
+10 to Dexterity (implicit)
12% increased maximum Energy Shield
+1 to Level of all Projectile Skills
13% increased Critical Damage Bonus
+3 to all Attributes"""

    advice = generate_tactical_advice(
        delta=delta,
        candidate_raw=candidate_raw,
        current_raw=current_raw,
        zone_id="G2_1",
        character_level=51,
        stage=BuildProgressionStage.LEVELING_33_51,
    )
    assert advice.verdict == Verdict.EQUIP_NOW
    assert "🟢" in advice.verdict_badge or "GANTI" in advice.verdict_badge
    assert "Sorrow Noose" in advice.tactical_headline
    assert "pertahanan" in advice.tactical_headline.lower() or "life" in advice.tactical_headline.lower()







