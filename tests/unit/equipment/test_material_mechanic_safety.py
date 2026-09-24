"""Unit and integration tests for material equipment build mechanic safety."""

import tempfile
from pathlib import Path
import pytest

from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.data_sufficiency import (
    RecommendationDataSufficiency,
    analyze_data_sufficiency,
)
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.equipment.mechanics import (
    KNOWN_SPECIAL_MECHANICS,
    MechanicImpactCertainty,
    ProjectionSupport,
    evaluate_mechanic_safety,
    lookup_special_mechanic,
    normalize_mechanic_key,
)
from companion.equipment.parser import parse_item_text
from companion.equipment.partial_projection import project_candidate_on_loadout
from companion.equipment.precedence import Verdict
from companion.equipment.schema import (
    ModifierScope,
    NormalizedModifier,
    NormalizedModifierType,
    SlotType,
)
from companion.state.provenance import VerificationState


KNIGHT_ERRANT_BOOTS = """Item Class: Boots
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

VICTORY_SOLES_BOOTS = """Item Class: Boots
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

PRESERVED_IRON_REFLEXES_BOOTS = """Item Class: Boots
Rarity: Rare
Titan Stride
Mail Sabatons
--------
Armour: 50
Evasion Rating: 45
--------
Requires: Level 15
--------
+80 to maximum Life
+35% to Fire Resistance
25% increased Movement Speed
Iron Reflexes — Unscalable Value
"""

STUN_THRESHOLD_ONLY_BOOTS = """Item Class: Boots
Rarity: Rare
Stun Guard Boots
Mail Sabatons
--------
Armour: 30
Evasion Rating: 20
--------
Requires: Level 10
--------
+30 to Stun Threshold
10% increased Movement Speed
"""

CANDIDATE_WITH_FIRE_BREAKER = """Item Class: Boots
Rarity: Rare
Flaming Greaves
Mail Sabatons
--------
Armour: 40
--------
Requires: Level 15
--------
Adds 10 to 20 Fire Damage to Attacks
+80 to maximum Life
25% increased Movement Speed
"""


def test_mechanic_registry_iron_reflexes_metadata():
    """Iron Reflexes must be registered with verified identity and unmodeled projection support."""
    assert "iron_reflexes" in KNOWN_SPECIAL_MECHANICS
    mech = lookup_special_mechanic("Iron Reflexes — Unscalable Value")
    assert mech.mechanic_id == "iron_reflexes"
    assert mech.canonical_name == "Iron Reflexes"
    assert mech.verification == VerificationState.VERIFIED
    assert mech.projection_support == ProjectionSupport.UNMODELED


def test_mechanic_key_normalization():
    """Special mechanic names normalize consistently to canonical snake_case keys."""
    assert normalize_mechanic_key("Iron Reflexes — Unscalable Value") == "iron_reflexes"
    assert normalize_mechanic_key("Iron Reflexes") == "iron_reflexes"
    assert normalize_mechanic_key("Chaos Inoculation") == "chaos_inoculation"


def test_knight_errant_replacement_gated_by_removed_iron_reflexes():
    """Replacing The Knight-errant with candidate lacking Iron Reflexes must NOT return EQUIP_NOW."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime_dir = Path(tmp_dir)
        char_id = "test_char"

        run_loadout_set_item(runtime_dir, char_id, "boots", KNIGHT_ERRANT_BOOTS)
        run_loadout_finalize(runtime_dir, char_id)
        run_baseline_set(
            runtime_dir,
            char_id,
            life=2000,
            fire_res=75,
            fire_raw=75,
            cold_res=75,
            cold_raw=75,
            lightning_res=75,
            lightning_raw=75,
            chaos_res=0,
            chaos_raw=0,
            strength=100,
            dexterity=100,
            intelligence=100,
            movement_speed=10,
            armour=500,
            evasion=500,
        )

        engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
        rec = engine.evaluate_candidate(
            item_text=VICTORY_SOLES_BOOTS,
            character_id=char_id,
            target_slot="boots",
        )

        # 1. Invariant: Must NOT return EQUIP_NOW
        assert rec.verdict != Verdict.EQUIP_NOW
        assert rec.verdict == Verdict.INSUFFICIENT_DATA

        # 2. Data sufficiency is conservative
        assert rec.sufficiency.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP
        assert not rec.sufficiency.is_sufficient_for_equip_now

        # 3. Warning mentions Iron Reflexes
        warning_found = any("Iron Reflexes" in r for r in rec.sufficiency.reasons) or "Iron Reflexes" in rec.verdict_reason
        assert warning_found

        # 4. Projection tracks removed mechanics
        assert len(rec.projection.removed_build_mechanics) == 1
        assert rec.projection.removed_build_mechanics[0].raw_text == "Iron Reflexes — Unscalable Value"
        assert len(rec.projection.added_build_mechanics) == 0

        # 5. CLI report exposes build mechanics and uncertainties
        report = rec.formatted_report
        assert "BUILD MECHANICS" in report
        assert "Iron Reflexes" in report
        assert "UNCERTAINTIES" in report


def test_candidate_added_unmodeled_mechanic_gated():
    """Adding an unmodeled special mechanic onto an item candidate must NOT return EQUIP_NOW."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime_dir = Path(tmp_dir)
        char_id = "test_char"

        # Current boots: plain boots without Iron Reflexes
        run_loadout_set_item(runtime_dir, char_id, "boots", STUN_THRESHOLD_ONLY_BOOTS)
        run_loadout_finalize(runtime_dir, char_id)
        run_baseline_set(
            runtime_dir,
            char_id,
            life=2000,
            fire_res=75,
            fire_raw=75,
            cold_res=75,
            cold_raw=75,
            lightning_res=75,
            lightning_raw=75,
            chaos_res=0,
            chaos_raw=0,
            strength=100,
            dexterity=100,
            intelligence=100,
            movement_speed=10,
        )

        engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
        rec = engine.evaluate_candidate(
            item_text=KNIGHT_ERRANT_BOOTS,
            character_id=char_id,
            target_slot="boots",
        )

        assert rec.verdict != Verdict.EQUIP_NOW
        assert rec.verdict == Verdict.INSUFFICIENT_DATA
        assert rec.sufficiency.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP
        assert len(rec.projection.added_build_mechanics) == 1
        assert any("Iron Reflexes" in r for r in rec.sufficiency.reasons)


def test_same_mechanic_preserved_allows_confident_equip():
    """When current and candidate both carry the same mechanic identity, the mechanic alone does not block EQUIP_NOW."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime_dir = Path(tmp_dir)
        char_id = "test_char"

        run_loadout_set_item(runtime_dir, char_id, "boots", KNIGHT_ERRANT_BOOTS)
        run_loadout_finalize(runtime_dir, char_id)
        run_baseline_set(
            runtime_dir,
            char_id,
            life=2000,
            fire_res=75,
            fire_raw=75,
            cold_res=75,
            cold_raw=75,
            lightning_res=75,
            lightning_raw=75,
            chaos_res=0,
            chaos_raw=0,
            strength=100,
            dexterity=100,
            intelligence=100,
            movement_speed=10,
            armour=500,
            evasion=500,
        )

        engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
        rec = engine.evaluate_candidate(
            item_text=PRESERVED_IRON_REFLEXES_BOOTS,
            character_id=char_id,
            target_slot="boots",
        )

        # Preserved mechanic does not block
        assert len(rec.projection.preserved_build_mechanics) == 1
        assert len(rec.projection.removed_build_mechanics) == 0
        assert len(rec.projection.added_build_mechanics) == 0
        assert rec.verdict == Verdict.EQUIP_NOW
        assert rec.sufficiency.sufficiency == RecommendationDataSufficiency.SUFFICIENT


def test_unrelated_unknown_affix_does_not_trigger_material_mechanic_gate():
    """Ordinary UNKNOWN_MODIFIER (e.g. Stun Threshold) does not block confident equip on clear upgrade."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime_dir = Path(tmp_dir)
        char_id = "test_char"

        run_loadout_set_item(runtime_dir, char_id, "boots", STUN_THRESHOLD_ONLY_BOOTS)
        run_loadout_finalize(runtime_dir, char_id)
        run_baseline_set(
            runtime_dir,
            char_id,
            life=2000,
            fire_res=75,
            fire_raw=75,
            cold_res=75,
            cold_raw=75,
            lightning_res=75,
            lightning_raw=75,
            chaos_res=0,
            chaos_raw=0,
            strength=100,
            dexterity=100,
            intelligence=100,
            movement_speed=10,
        )

        engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
        rec = engine.evaluate_candidate(
            item_text=VICTORY_SOLES_BOOTS,
            character_id=char_id,
            target_slot="boots",
        )

        assert rec.verdict == Verdict.EQUIP_NOW
        assert rec.sufficiency.sufficiency == RecommendationDataSufficiency.SUFFICIENT


def test_material_mechanic_with_verified_build_breaker_precedence_is_reject():
    """When a candidate violates a verified build breaker, verdict is REJECT even if mechanic changes exist."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime_dir = Path(tmp_dir)
        char_id = "test_char"

        run_loadout_set_item(runtime_dir, char_id, "boots", KNIGHT_ERRANT_BOOTS)
        run_loadout_finalize(runtime_dir, char_id)
        run_baseline_set(
            runtime_dir,
            char_id,
            life=2000,
            fire_res=75,
            fire_raw=75,
            cold_res=75,
            cold_raw=75,
            lightning_res=75,
            lightning_raw=75,
            chaos_res=0,
            chaos_raw=0,
            strength=100,
            dexterity=100,
            intelligence=100,
            movement_speed=10,
        )

        engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
        rec = engine.evaluate_candidate(
            item_text=CANDIDATE_WITH_FIRE_BREAKER,
            character_id=char_id,
            target_slot="boots",
        )

        assert rec.verdict == Verdict.REJECT
        assert "BUILD_BREAKER" in rec.flags


def test_material_mechanic_with_stale_baseline_remains_insufficient_data():
    """Stale baseline + removed mechanic stays conservative with INSUFFICIENT_DATA."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime_dir = Path(tmp_dir)
        char_id = "test_char"

        run_loadout_set_item(runtime_dir, char_id, "boots", KNIGHT_ERRANT_BOOTS)
        run_loadout_finalize(runtime_dir, char_id)
        # Baseline anchored to older revision
        run_baseline_set(
            runtime_dir,
            char_id,
            life=2000,
            fire_res=75,
            fire_raw=75,
            anchored_revision=999,
        )

        engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
        rec = engine.evaluate_candidate(
            item_text=VICTORY_SOLES_BOOTS,
            character_id=char_id,
            target_slot="boots",
        )

        assert rec.verdict == Verdict.INSUFFICIENT_DATA
        assert rec.sufficiency.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP
