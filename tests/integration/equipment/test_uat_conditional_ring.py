"""UAT Scenario 2: High-life ring removing 40% Lightning Res causing unmitigated deficit."""

from pathlib import Path
import pytest
from companion.equipment.schema import SlotType
from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.precedence import Verdict

CURRENT_RING = """Item Class: Rings
Rarity: Rare
Storm Circle
Topaz Ring
--------
Requirements:
Level: 30
--------
Item Level: 35
--------
+40% to Lightning Resistance
+20 to Strength
"""

CANDIDATE_RING = """Item Class: Rings
Rarity: Rare
Blood Knot
Coral Ring
--------
Requirements:
Level: 50
--------
Item Level: 55
--------
+90 to maximum Life
+30 to Strength
"""


def test_uat_conditional_ring_res_loss(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "fubgun_ignite"

    # Equipped ring has +40% lightning res
    run_loadout_set_item(runtime_dir, char_id, "ring1", CURRENT_RING)
    run_loadout_finalize(runtime_dir, char_id)

    # Baseline has 75% effective res, no overcap buffer (raw 75)
    run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=2000,
        lightning_res=75,
        lightning_raw=75,
        max_lightning_res=75,
        str=120,
    )

    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(
        CANDIDATE_RING,
        target_slot="ring1",
        character_id=char_id,
    )

    assert rec.slot == SlotType.RING_1
    # Net delta: -40% lightning res, +90 life
    assert rec.projection.lightning_res.delta == -40.0
    assert rec.projection.life.delta == 90.0
    # Leaves character with 35% res (a 40% deficit!)
    assert rec.projection.lightning_res.projected_absolute == 35
    # Must NOT be EQUIP_NOW because it breaks resistance cap; must be CONDITIONAL_UPGRADE
    assert rec.verdict == Verdict.CONDITIONAL_UPGRADE
    assert "UNMITIGATED_DEFICIT" in rec.flags
