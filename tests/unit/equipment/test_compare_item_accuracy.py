"""Regression and accuracy tests for user-facing item comparison.

Ensures:
1. PoE2 item parser accurately maps off-hand Foci (not Helmet) and Two-Handed melee weapons (not 1H).
2. Boots Movement Speed losses do not produce misleading '+0 Life, +0% Resistance' or 'Life/Resistance trade-off' reasons.
3. Material DPS drops on non-weapon slots (Amulets, Rings) cannot be awarded unconditional EQUIP_NOW.
4. Tactical advisor honors INSUFFICIENT_DATA and does not emit confident EQUIP_NOW when baseline is stale/missing.
5. Tactical advisor recognizes any boots movement speed regression in its headline.
6. Dashboard API reliably resolves all loadout slot items (including rings and weapons).
7. Dashboard formatted_report is synchronized with authoritative tactical rejection.
"""

from pathlib import Path
import pytest

from companion.equipment.parser import parse_item_text
from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta
from companion.equipment.fubgun_priorities import evaluate_fubgun_equipment_policy
from companion.equipment.precedence import Verdict
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.schema import SlotOccupancy, SlotType, WeaponSetContext
from companion.equipment.tactical_advisor import generate_tactical_advice
from companion.dashboard_api import evaluate_item_payload, get_current_raw
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.loadout_cli import save_loadout


def test_parse_foci_offhand_slot_and_topology() -> None:
    text = (
        "Item Class: Foci\n"
        "Rarity: Rare\n"
        "Crystal Focus\n"
        "Antler Focus\n"
        "--------\n"
        "Requirements:\n"
        "Level: 18\n"
        "--------\n"
        "+20 to maximum Energy Shield\n"
        "+15% to Cold Resistance"
    )
    item = parse_item_text(text)
    assert item.slot == SlotType.OFF_HAND
    assert item.slot_occupancy == SlotOccupancy.OFF_HAND
    assert item.slot_conflict_topology.occupied_slots == [SlotType.OFF_HAND]
    assert item.slot_conflict_topology.is_known is True


def test_parse_two_handed_melee_weapons_topology() -> None:
    text_2h_sword = (
        "Item Class: Two Hand Swords\n"
        "Rarity: Rare\n"
        "Executioner Blade\n"
        "Colossus Greatsword\n"
        "--------\n"
        "Requirements:\n"
        "Level: 25\n"
        "--------\n"
        "+40% increased Physical Damage"
    )
    item = parse_item_text(text_2h_sword)
    assert item.slot == SlotType.MAIN_HAND
    assert item.slot_occupancy == SlotOccupancy.TWO_HAND
    assert item.slot_conflict_topology.occupied_slots == [SlotType.MAIN_HAND, SlotType.OFF_HAND]
    assert item.slot_conflict_topology.allowed_companion_slots == []

    text_2h_mace = (
        "Item Class: Two Hand Maces\n"
        "Rarity: Rare\n"
        "Skull Crusher\n"
        "Stone Maul\n"
        "--------\n"
        "Requirements:\n"
        "Level: 20\n"
        "--------\n"
        "+35% increased Physical Damage"
    )
    item_mace = parse_item_text(text_2h_mace)
    assert item_mace.slot == SlotType.MAIN_HAND
    assert item_mace.slot_occupancy == SlotOccupancy.TWO_HAND
    assert item_mace.slot_conflict_topology.occupied_slots == [SlotType.MAIN_HAND, SlotType.OFF_HAND]


def test_boots_movement_speed_loss_reason_accuracy() -> None:
    delta = PobEquipmentDelta(
        slot="Boots",
        candidate_id=1,
        candidate_name="Heavy Iron Boots",
        armour_delta=50,
        movement_speed_delta=-10.0,
        ehp_delta=2.0,
    )
    rec = evaluate_fubgun_equipment_policy(delta)
    assert rec.verdict == Verdict.REJECT
    assert "+0 Life, +0% Resistance" not in rec.reason
    assert "Movement Speed" in rec.reason


def test_boots_movement_speed_tradeoff_with_life_and_res_reason_accuracy() -> None:
    delta = PobEquipmentDelta(
        slot="Boots",
        candidate_id=2,
        candidate_name="Tank Boots",
        life_delta=50,
        fire_res_delta=20,
        cold_res_delta=20,
        movement_speed_delta=-10.0,
        ehp_delta=15.0,
    )
    rec = evaluate_fubgun_equipment_policy(delta)
    assert rec.verdict == Verdict.CONDITIONAL_UPGRADE
    assert "Life/Resistance trade-off" not in rec.reason
    assert "Movement Speed" in rec.reason


def test_amulet_material_dps_loss_downgrades_to_conditional_upgrade() -> None:
    delta = PobEquipmentDelta(
        slot="Amulet",
        candidate_id=3,
        candidate_name="Defensive Amulet",
        life_delta=25,
        fire_res_delta=15,
        dps_delta=-12.5,
        ehp_delta=8.0,
    )
    rec = evaluate_fubgun_equipment_policy(delta)
    assert rec.verdict == Verdict.CONDITIONAL_UPGRADE
    assert "DPS" in rec.reason or "damage" in rec.reason.lower()


def test_tactical_advisor_respects_insufficient_baseline_verdict() -> None:
    delta = PobEquipmentDelta(
        slot="Helmet",
        candidate_id=4,
        candidate_name="Kraken Dome",
        life_delta=10,
        fire_res_delta=3,
        cold_res_delta=10,
        armour_delta=20,
    )
    tactical = generate_tactical_advice(
        delta=delta,
        candidate_raw="Item Class: Helmets\nRarity: Rare\nKraken Dome\nVisored Helm\n--------\nArmour: 70\n--------\n+35 to maximum Life",
        current_raw="Item Class: Helmets\nRarity: Rare\nDire Horn\nIron Cap\n--------\nArmour: 50\n--------\n+25 to maximum Life",
        zone_id="G2_1",
        character_level=19,
        base_verdict=Verdict.INSUFFICIENT_DATA,
    )
    assert tactical.verdict == Verdict.INSUFFICIENT_DATA
    assert "GANTI SEKARANG" not in tactical.verdict_badge
    assert "BASELINE" in tactical.verdict_badge or "DATA" in tactical.verdict_badge


def test_tactical_advisor_boots_moderate_movement_speed_loss_headline() -> None:
    delta = PobEquipmentDelta(
        slot="Boots",
        candidate_id=5,
        candidate_name="Slow Sabatons",
        movement_speed_delta=-5.0,
        armour_delta=10,
        ehp_delta=-1.5,
    )
    tactical = generate_tactical_advice(
        delta=delta,
        candidate_raw="Item Class: Boots\nRarity: Rare\nSlow Sabatons\nMail Sabatons\n--------",
        current_raw="Item Class: Boots\nRarity: Rare\nFast Boots\nMail Sabatons\n--------",
        zone_id="G2_1",
        character_level=19,
    )
    assert tactical.verdict == Verdict.REJECT
    assert "Movement Speed" in tactical.tactical_headline


def test_dashboard_api_get_current_raw_resolves_all_loadout_slots(tmp_path: Path) -> None:
    lo = EquippedLoadout.create_draft(character_id="hero_test", loadout_id="lo_test")
    item_helmet = parse_item_text("Item Class: Helmets\nRarity: Rare\nTest Helm\nVisored Helm\n--------\nArmour: 50")
    item_ring1 = parse_item_text("Item Class: Rings\nRarity: Rare\nRing One\nIron Ring\n--------")
    item_ring2 = parse_item_text("Item Class: Rings\nRarity: Rare\nRing Two\nIron Ring\n--------")
    item_wep1 = parse_item_text("Item Class: Crossbows\nRarity: Rare\nCrossbow One\nVarnished Crossbow\n--------")

    lo.set_slot(SlotType.HELMET, item_helmet)
    lo.set_slot(SlotType.RING_1, item_ring1)
    lo.set_slot(SlotType.RING_2, item_ring2)
    lo.set_slot(SlotType.MAIN_HAND, item_wep1, weapon_set=WeaponSetContext.WEAPON_SET_1)
    lo.finalize()
    save_loadout(tmp_path, lo)

    raw_r1 = get_current_raw(tmp_path, "hero_test", "Ring 1")
    assert "Ring One" in raw_r1
    raw_r2 = get_current_raw(tmp_path, "hero_test", "Ring 2")
    assert "Ring Two" in raw_r2
    raw_w1 = get_current_raw(tmp_path, "hero_test", "Weapon 1")
    assert "Crossbow One" in raw_w1


def test_dashboard_api_formatted_report_synchronizes_with_tactical_rejection(tmp_path: Path) -> None:
    lo = EquippedLoadout.create_draft(character_id="hero_test", loadout_id="lo_test")
    item_cuirass = parse_item_text(
        "Item Class: Body Armours\n"
        "Rarity: Rare\n"
        "Glyph Pelt\n"
        "Iron Cuirass\n"
        "--------\n"
        "Armour: 98\n"
        "--------\n"
        "+30 to maximum Life\n"
        "+15% to Fire Resistance\n"
        "+12% to Cold Resistance"
    )
    lo.set_slot(SlotType.BODY_ARMOUR, item_cuirass)
    lo.finalize()
    save_loadout(tmp_path, lo)

    cand_text = (
        "Item Class: Body Armours\n"
        "Rarity: Rare\n"
        "Maelström Keep\n"
        "Iron Cuirass\n"
        "--------\n"
        "Armour: 180\n"
        "--------\n"
        "+23 to maximum Life\n"
        "+5.8 Life Regeneration per second\n"
        "-12 to Strength"
    )
    res = evaluate_item_payload(
        {"raw_text": cand_text, "character_id": "hero_test", "slot": "body_armour", "zone": "G2_1"},
        runtime_dir=tmp_path,
        pob_session=None,
    )
    assert res.get("verdict") == "REJECT"
    assert "REJECT" in res.get("formatted_report")
    assert "EQUIP NOW" not in res.get("formatted_report")
    assert "CONDITIONAL UPGRADE" not in res.get("formatted_report")
