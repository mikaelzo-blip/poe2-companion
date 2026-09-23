"""FIXTURE-BASED INTEGRATION TESTS Scenario 6: Unknown fire modifier blocks EQUIP_NOW and triggers High-Risk Unknown Gate."""

from pathlib import Path
import pytest
from companion.equipment.schema import SlotType
from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.rules import BuildBreakerCertainty, BuildProgressionStage
from companion.equipment.precedence import Verdict

UNKNOWN_RING = """Item Class: Rings
Rarity: Rare
Whispering Band
Gold Ring
--------
Requirements:
Level: 60
--------
Item Level: 65
--------
+100 to maximum Life
+40% to Cold Resistance
+40% to Lightning Resistance
Gain 10% of Physical Damage as Extra Fire Damage during Focus
"""


def test_uat_unknown_fire_modifier_high_risk_gate(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "fubgun_ignite"

    run_loadout_set_item(
        runtime_dir,
        char_id,
        "ring2",
        "Item Class: Rings\nRarity: Normal\nIron Ring\n--------\n",
    )
    run_loadout_finalize(runtime_dir, char_id)

    # Character baseline has space for more life and res
    run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=2000,
        fire_res=75,
        fire_raw=75,
        cold_res=50,
        cold_raw=50,
        lightning_res=50,
        lightning_raw=50,
    )

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        UNKNOWN_RING,
        target_slot="ring2",
        character_id=char_id,
        stage=BuildProgressionStage.EARLY_ENDGAME,
    )

    assert rec.slot == SlotType.RING_2
    assert rec.safety_eval.certainty == BuildBreakerCertainty.UNKNOWN_APPLICABILITY
    # High-Risk Unknown Gate prevents EQUIP_NOW, forcing CONDITIONAL_UPGRADE with HIGH_RISK flag
    assert rec.verdict == Verdict.CONDITIONAL_UPGRADE
    assert "HIGH_RISK" in rec.flags
    assert "HIGH RISK UNKNOWN WARNING" in rec.formatted_report
