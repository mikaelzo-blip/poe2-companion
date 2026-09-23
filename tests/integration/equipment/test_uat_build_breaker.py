"""UAT Scenario 3: Shared ring with flat fire damage to attacks triggering build breaker REJECT."""

from pathlib import Path
import pytest
from companion.equipment.schema import SlotType
from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.rules import BuildBreakerCertainty, BuildProgressionStage
from companion.equipment.precedence import Verdict

BREAKER_RING = """Item Class: Rings
Rarity: Rare
Pyre Touch
Iron Ring
--------
Requirements:
Level: 45
--------
Item Level: 50
--------
+80 to maximum Life
+35% to Fire Resistance
+35% to Cold Resistance
Adds 12 to 24 Fire Damage to Attacks
"""


def test_uat_flat_fire_ring_build_breaker(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "fubgun_ignite"

    run_loadout_set_item(
        runtime_dir,
        char_id,
        "ring1",
        "Item Class: Rings\nRarity: Normal\nIron Ring\n--------\n",
    )
    run_loadout_finalize(runtime_dir, char_id)

    run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=2500,
        fire_res=75,
        fire_raw=75,
    )

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        BREAKER_RING,
        target_slot="ring1",
        character_id=char_id,
        stage=BuildProgressionStage.EARLY_ENDGAME,
    )

    assert rec.slot == SlotType.RING_1
    assert rec.safety_eval.certainty == BuildBreakerCertainty.VERIFIED_BUILD_BREAKER
    assert rec.verdict == Verdict.REJECT
    assert "BUILD_BREAKER" in rec.flags
    assert "BUILD BREAKER DETECTED" in rec.formatted_report
    assert "Harmful added Fire damage" in rec.verdict_reason
