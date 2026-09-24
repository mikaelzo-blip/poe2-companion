"""Regression tests using live PoE2 clipboard item text for The Knight-errant Mail Sabatons."""

import pytest
from companion.equipment.parser import parse_item_text, validate_poe2_item_envelope
from companion.equipment.contribution import build_item_contribution
from companion.equipment.schema import (
    ModifierScope,
    NormalizedModifierType,
    SlotOccupancy,
    SlotType,
)
from companion.state.provenance import VerificationState
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.equipment.precedence import Verdict
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.live_watcher import format_short_human_recommendation

BERYL_BOOTS_RAW = """Item Class: Boots
Rarity: Magic
Beryl Mail Sabatons of the Mongoose
Mail Sabatons
--------
Armour: 22
Evasion Rating: 17
--------
Requires: Level 6
--------
Item Level: 15
--------
{ Prefix Modifier "Beryl" (Tier: 9) — Mana }
+13(10-14) to maximum Mana
{ Suffix Modifier "of the Mongoose" (Tier: 8) — Attribute }
+5(5-8) to Dexterity
"""

VICTORY_SOLES_BOOTS_RAW = """Item Class: Boots
Rarity: Rare
Victory Soles
Mail Sabatons
--------
Armour: 40
Evasion Rating: 35
--------
Requires: Level 15
--------
+80 to maximum Life
+35% to Fire Resistance
+30% to Cold Resistance
25% increased Movement Speed
"""

KNIGHT_ERRANT_BOOTS_RAW = """Item Class: Boots
Rarity: Unique
The Knight-errant
Mail Sabatons
--------
Armour: 32 (augmented)
Evasion Rating: 25 (augmented)
--------
Requires: Level 6
--------
Item Level: 15
--------
{ Unique Modifier — Armour, Evasion }
45(30-50)% increased Armour and Evasion
{ Unique Modifier }
+30(30-50) to Stun Threshold
{ Unique Modifier — Speed }
10% increased Movement Speed
{ Unique Modifier — Armour, Evasion }
Iron Reflexes — Unscalable Value
{ Unique Modifier }
+45(30-50) to Ailment Threshold
--------
Some search forever for their path.
"""


def test_knight_errant_boots_regression_fixture():
    # 1. Valid PoE2 item accepted by envelope validation
    validate_poe2_item_envelope(KNIGHT_ERRANT_BOOTS_RAW)

    # 2. Parse item
    item = parse_item_text(KNIGHT_ERRANT_BOOTS_RAW)

    # Identity & Rarity
    assert item.name == "The Knight-errant"
    assert item.base_type == "Mail Sabatons"
    assert item.rarity == "unique"

    # Slot & Occupancy
    assert item.slot == SlotType.BOOTS
    assert item.slot_occupancy == SlotOccupancy.SINGLE_SLOT
    assert item.slot_conflict_topology.occupied_slots == [SlotType.BOOTS]
    assert item.slot_conflict_topology.conflicting_slots == [SlotType.BOOTS]
    assert item.slot_conflict_topology.is_known is True

    # Requirements & Properties
    assert item.required_level == 6
    assert item.required_str == 0
    assert item.required_dex == 0
    assert item.required_int == 0
    assert item.item_level == 15

    # Displayed Defenses
    assert item.local_armour == 32
    assert item.local_evasion == 25
    assert item.local_energy_shield == 0

    # Annotations filtered from modifiers and stored as evidence
    assert len(item.annotations) == 5
    assert "{ Unique Modifier — Armour, Evasion }" in item.annotations
    assert "{ Unique Modifier }" in item.annotations
    assert "{ Unique Modifier — Speed }" in item.annotations
    assert not any("{" in m.raw_text for m in item.modifiers)
    assert not any("modifier" in m.raw_text.lower() for m in item.modifiers)

    # Flavor text separated and not in modifiers
    assert item.flavor_text == "Some search forever for their path."
    assert not any(m.raw_text == "Some search forever for their path." for m in item.modifiers)

    # Exactly 5 real modifiers
    assert len(item.modifiers) == 5

    # 1) Local increased Armour/Evasion
    local_defense_mod = next(
        m for m in item.modifiers if m.modifier_type == NormalizedModifierType.LOCAL_ARMOUR_AND_EVASION
    )
    assert local_defense_mod.scope == ModifierScope.LOCAL_ITEM_STAT
    assert local_defense_mod.value == 45.0
    assert local_defense_mod.raw_text == "45(30-50)% increased Armour and Evasion"

    # 2) Movement Speed
    ms_mod = next(m for m in item.modifiers if m.modifier_type == NormalizedModifierType.MOVEMENT_SPEED)
    assert ms_mod.scope == ModifierScope.GLOBAL_CHARACTER_STAT
    assert ms_mod.value == 10.0

    # 3) Iron Reflexes special mechanic text
    iron_reflexes_mod = next(
        m for m in item.modifiers if m.modifier_type == NormalizedModifierType.SPECIAL_MECHANIC
    )
    assert iron_reflexes_mod.scope == ModifierScope.BUILD_MECHANIC
    assert iron_reflexes_mod.verification_state == VerificationState.UNKNOWN
    assert iron_reflexes_mod.raw_text == "Iron Reflexes — Unscalable Value"

    # 4 & 5) Unsupported Stun/Ailment Threshold remain unknown
    unknown_mods = [m for m in item.modifiers if m.modifier_type == NormalizedModifierType.UNKNOWN_MODIFIER]
    assert len(unknown_mods) == 2
    unknown_texts = {m.raw_text for m in unknown_mods}
    assert "+30(30-50) to Stun Threshold" in unknown_texts
    assert "+45(30-50) to Ailment Threshold" in unknown_texts
    for umod in unknown_mods:
        assert umod.scope == ModifierScope.UNKNOWN_SCOPE
        assert umod.verification_state == VerificationState.UNKNOWN

    # ItemContribution aggregation and no-double-count invariant
    contrib = build_item_contribution(item)
    assert contrib.slot == SlotType.BOOTS
    assert contrib.local_armour == 32
    assert contrib.local_evasion == 25
    assert contrib.local_energy_shield == 0
    assert contrib.movement_speed_delta == 10.0
    assert contrib.life_delta == 0.0
    assert contrib.fire_res_delta == 0.0
    # No double counting: local % increased Armour/Evasion is NOT in global or unknown modifiers
    assert not any(m.modifier_type == NormalizedModifierType.LOCAL_ARMOUR_AND_EVASION for m in contrib.global_modifiers)
    assert not any(m.modifier_type == NormalizedModifierType.LOCAL_ARMOUR_AND_EVASION for m in contrib.unknown_modifiers)
    # Iron Reflexes is in build_mechanic_modifiers with UNKNOWN verification
    assert len(contrib.build_mechanic_modifiers) == 1
    assert contrib.build_mechanic_modifiers[0].raw_text == "Iron Reflexes — Unscalable Value"
    assert contrib.build_mechanic_modifiers[0].verification_state == VerificationState.UNKNOWN
    # Unknown modifiers only contain Stun and Ailment threshold
    assert len(contrib.unknown_modifiers) == 2


def test_knight_errant_vs_beryl_regression_verdict(tmp_path):
    """The Knight-errant vs Beryl regression must evaluate to REJECT even with baseline MISSING.

    Per spec clarifications:
    - An UNMODELED SPECIAL_MECHANIC such as Iron Reflexes must not be treated as a quantified/proven negative by itself.
    - KEEP CURRENT / REJECT should be justified by verified item-level regressions:
      * Movement Speed loss (-10%)
      * Armour loss (-10)
      * Evasion loss (-8)
      * lack of meaningful compensating gains (+5 Dex does not compensate)
    - Iron Reflexes removal should be shown as an additional material uncertainty / reason not to switch,
      not assigned an invented numeric value.
    """
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_id = "test_player"

    # Set up loadout with The Knight-errant in boots (baseline is MISSING)
    run_loadout_set_item(runtime_dir, char_id, "boots", KNIGHT_ERRANT_BOOTS_RAW)
    run_loadout_finalize(runtime_dir, char_id)

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        item_text=BERYL_BOOTS_RAW,
        character_id=char_id,
        target_slot=SlotType.BOOTS,
        stage=BuildProgressionStage.LEVELING_15_32,
    )

    # 1. Must be REJECT (NOT INSUFFICIENT_DATA)
    assert rec.verdict == Verdict.REJECT
    assert "CLEAR_DOWNGRADE" in rec.flags

    # 2. Verdict reason cites verified item-level regressions and lack of compensating gains
    assert "Movement Speed" in rec.verdict_reason
    assert "Armour" in rec.verdict_reason
    assert "Evasion" in rec.verdict_reason

    # 3. Iron Reflexes is tracked as unmodeled removed mechanic (uncertainty, not invented score)
    assert len(rec.projection.removed_build_mechanics) == 1
    assert "Iron Reflexes" in rec.projection.removed_build_mechanics[0].raw_text
    assert "Iron Reflexes" in rec.verdict_reason
    assert "uncertainty" in rec.verdict_reason.lower()
    assert not hasattr(rec, "score_delta")  # Strictly non-scalar, never invented value

    # 4. Formatted human output displays losses and rejection
    report = format_short_human_recommendation(rec, vs_item_name="The Knight-errant")
    assert "🔴 REJECT / KEEP CURRENT" in report
    assert "vs The Knight-errant" in report
    assert "-10% Movement Speed" in report
    assert "-10 Armour" in report
    assert "-8 Evasion" in report


def test_one_sided_safe_negative_positive_candidate_held_insufficient(tmp_path):
    """Candidates with meaningful positive gains must NOT be allowed to EQUIP_NOW when baseline is missing or mechanics are unmodeled."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_id = "test_player"

    run_loadout_set_item(runtime_dir, char_id, "boots", KNIGHT_ERRANT_BOOTS_RAW)
    run_loadout_finalize(runtime_dir, char_id)

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        item_text=VICTORY_SOLES_BOOTS_RAW,
        character_id=char_id,
        target_slot=SlotType.BOOTS,
        stage=BuildProgressionStage.LEVELING_15_32,
    )

    # Candidate has +80 Life and +35% Fire Res, but baseline is missing and Iron Reflexes is removed:
    # It must NOT be EQUIP_NOW, but safely held as INSUFFICIENT_DATA
    assert rec.verdict != Verdict.EQUIP_NOW
    assert rec.verdict == Verdict.INSUFFICIENT_DATA
    assert not rec.sufficiency.is_sufficient_for_equip_now
