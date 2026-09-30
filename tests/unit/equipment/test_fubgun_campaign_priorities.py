"""TDD tests for verified Fubgun campaign gear priorities and unknown-mod materiality."""

from pathlib import Path
import pytest

from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.data_sufficiency import (
    DataSufficiencyResult,
    RecommendationDataSufficiency,
    analyze_data_sufficiency,
    is_material_unsupported_modifier,
)
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.live_watcher import (
    evaluate_live_candidate,
    format_short_human_recommendation,
)
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.equipment.parser import parse_item_text
from companion.equipment.precedence import Verdict
from companion.equipment.rules import BuildBreakerCertainty, BuildBreakerEvaluation, BuildProgressionStage
from companion.equipment.schema import SlotType
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore

BRIMSTONE_VEIL_HELMET_RAW = """Item Class: Helmets
Rarity: Rare
Brimstone Veil
Advanced Chain Tiara
--------
Evasion Rating: 28
Energy Shield: 16
--------
Requirements:
Level: 14
Dex: 15
Int: 15
--------
Item Level: 18
--------
+35 to Accuracy Rating
+18 to maximum Mana
1.5 Life Regenerated per second
11% increased Item Rarity
"""

KRAKEN_DOME_HELMET_RAW = """Item Class: Helmets
Rarity: Rare
Kraken Dome
Great Helmet
--------
Armour: 45
--------
Requirements:
Level: 15
Str: 22
--------
Item Level: 19
--------
+20 to maximum Life
+7% to Lightning Resistance
1.2 Life Regenerated per second
8% increased Item Rarity
"""


def test_helmet_unsupported_mods_materiality_during_campaign():
    """Unsupported Mana, Life Regen, Rarity, Light Radius, Accuracy on campaign helmet must NOT be material."""
    non_material_helmet_mods = [
        "+18 to maximum Mana",
        "1.5 Life Regenerated per second",
        "11% increased Item Rarity",
        "15% increased Light Radius",
        "+35 to Accuracy Rating",
    ]

    for mod_text in non_material_helmet_mods:
        assert not is_material_unsupported_modifier(
            mod_text,
            slot=SlotType.HELMET,
            stage=BuildProgressionStage.LEVELING_15_32,
        ), f"Expected '{mod_text}' to NOT be material on campaign helmet"

    # Genuinely material effects must still be preserved conservatively
    material_effects = [
        "Adds 1 to 4 Chaos Damage to Attacks",
        "Armour applies to Chaos Damage from Hits",
        "Hits Intimidate Enemies for 4 Seconds",
        "Curse Enemies with Despair on Hit",
        "10% increased Cooldown Recovery Rate",
    ]
    for mod_text in material_effects:
        assert is_material_unsupported_modifier(
            mod_text,
            slot=SlotType.HELMET,
            stage=BuildProgressionStage.LEVELING_15_32,
        ), f"Expected '{mod_text}' to remain material on campaign helmet"


def test_real_live_helmet_regression_brimstone_veil_vs_kraken_dome(tmp_path: Path):
    """Real live helmet regression: Brimstone Veil vs Kraken Dome must favor Kraken Dome (EQUIP_NOW)."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_id = "test_helmet_char"

    store = CharacterStateStore(runtime_dir)
    store.save_character(
        CharacterState(
            character_id=char_id,
            character_name="Hunter",
            build_progression={"active_stage": "lvl 15-32"},
        )
    )
    store.set_active_character(char_id)

    # Equip Brimstone Veil in loadout
    run_loadout_set_item(runtime_dir, char_id, "helmet", BRIMSTONE_VEIL_HELMET_RAW)
    run_loadout_finalize(runtime_dir, char_id)

    # Establish baseline with level 15 stats (Str 30, Dex 30, Int 30 to meet requirements)
    run_baseline_set(
        runtime_dir,
        char_id,
        life=350,
        fire_res=20,
        cold_res=15,
        lightning_res=10,
        chaos_res=-10,
        movement_speed=15,
        strength=30,
        dexterity=30,
        intelligence=30,
    )

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        item_text=KRAKEN_DOME_HELMET_RAW,
        character_id=char_id,
        target_slot=SlotType.HELMET,
        stage=BuildProgressionStage.LEVELING_15_32,
    )

    # 1. Candidate must NOT become INSUFFICIENT_DATA due to unsupported Mana/Life Regen
    assert rec.verdict != Verdict.INSUFFICIENT_DATA
    # 2. Must recommend EQUIP_NOW (Life + Lightning Resistance match Fubgun priority)
    assert rec.verdict == Verdict.EQUIP_NOW

    # 3. Report/Guidance should explain Life + Resistance match Fubgun campaign priority
    report = format_short_human_recommendation(rec, vs_item_name="Brimstone Veil")
    assert "🟢 EQUIP NOW" in report
    assert "+20 Life" in report
    assert "+7% Lightning Res" in report
    assert "Fubgun" in report or "Resistance > Life" in report or "priority" in report.lower()


def test_boots_movement_speed_campaign_priority(tmp_path: Path):
    """Movement speed is mandatory / highest slot-specific priority on boots."""
    from companion.equipment.fubgun_priorities import get_fubgun_slot_priority_note

    note = get_fubgun_slot_priority_note(SlotType.BOOTS, BuildProgressionStage.LEVELING_15_32)
    assert "Movement Speed" in note
    assert "Boots" in note


def test_rings_flat_damage_offensive_priority_during_campaign():
    """Flat damage to attacks is recognized as an offensive priority on rings/gloves in campaign."""
    from companion.equipment.fubgun_priorities import get_fubgun_slot_priority_note

    note_rings = get_fubgun_slot_priority_note(SlotType.RING_1, BuildProgressionStage.LEVELING_15_32)
    assert "flat damage" in note_rings.lower() or "damage to attacks" in note_rings.lower()

    note_gloves = get_fubgun_slot_priority_note(SlotType.GLOVES, BuildProgressionStage.LEVELING_15_32)
    assert "flat damage" in note_gloves.lower() or "damage to attacks" in note_gloves.lower()


def test_body_armour_campaign_priority():
    """High Armour or Armour/Evasion hybrid is primary defense priority on Body Armour."""
    from companion.equipment.fubgun_priorities import get_fubgun_slot_priority_note

    note = get_fubgun_slot_priority_note(SlotType.BODY_ARMOUR, BuildProgressionStage.LEVELING_15_32)
    assert "Armour" in note
    assert "Evasion" in note or "hybrid" in note.lower()


def test_chaos_resistance_is_a_primary_gain_for_fubgun_equipment():
    from companion.equipment.fubgun_priorities import evaluate_fubgun_equipment_policy
    from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta

    delta = PobEquipmentDelta(
        slot="Gloves",
        candidate_id=101,
        candidate_name="Chaos Mitts",
        current_item_name="Cloth Gloves",
        chaos_res_delta=30,
    )

    recommendation = evaluate_fubgun_equipment_policy(
        delta,
        stage=BuildProgressionStage.LEVELING_15_32,
        use_color=False,
    )

    assert recommendation.verdict != Verdict.REJECT
    assert "+30% Chaos Res" in recommendation.formatted_output


def test_chaos_resistance_loss_blocks_unconditional_life_upgrade():
    from companion.equipment.fubgun_priorities import evaluate_fubgun_equipment_policy
    from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta

    delta = PobEquipmentDelta(
        slot="Gloves",
        candidate_id=102,
        candidate_name="Life Mitts",
        current_item_name="Chaos Mitts",
        life_delta=20,
        chaos_res_delta=-30,
    )

    recommendation = evaluate_fubgun_equipment_policy(
        delta,
        stage=BuildProgressionStage.LEVELING_15_32,
        use_color=False,
    )

    assert recommendation.verdict != Verdict.EQUIP_NOW
    assert "-30% Chaos Res" in recommendation.formatted_output


def test_weapon_dps_gain_with_large_ehp_loss_is_conditional():
    from companion.equipment.fubgun_priorities import evaluate_fubgun_weapon_policy
    from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta

    delta = PobEquipmentDelta(
        slot="Weapon 1",
        candidate_id=103,
        candidate_name="Glass Cannon",
        current_item_name="Tower Shield Setup",
        dps_delta=5.0,
        ehp_delta=-350.0,
        armour_delta=-800,
    )

    recommendation = evaluate_fubgun_weapon_policy(delta, use_color=False)

    assert recommendation.verdict == Verdict.CONDITIONAL_UPGRADE
    assert "-350.00 Total EHP" in recommendation.formatted_output


def test_weapon_empty_slot_does_not_recommend_rejected_candidate():
    from companion.equipment.fubgun_priorities import evaluate_dual_weapon_policy
    from companion.equipment.pob2_equipment_advisor import PobEquipmentDelta

    delta1 = PobEquipmentDelta(
        slot="Weapon 1",
        candidate_id=104,
        candidate_name="Weak Weapon",
        dps_delta=-10.0,
    )
    delta2 = delta1.model_copy(update={"slot": "Weapon 2"})

    recommendation = evaluate_dual_weapon_policy(
        delta1,
        delta2,
        empty_slot2=True,
        use_color=False,
    )

    assert recommendation.recommended_slot is None
    assert "Neither placement recommended" in recommendation.summary_verdict


def test_weapon_lvl15_32_fubgun_priority():
    """Weapon lvl 15-32 priority: highest damage crossbow, % Physical desirable, Attack speed low value."""
    from companion.equipment.fubgun_priorities import get_fubgun_slot_priority_note

    note = get_fubgun_slot_priority_note(SlotType.MAIN_HAND, BuildProgressionStage.LEVELING_15_32)
    assert "Crossbow" in note or "crossbow" in note
    assert "Varnished" in note or "Physical" in note

