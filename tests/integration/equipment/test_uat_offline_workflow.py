"""UAT Scenario 7: Complete offline workflow from capture to promotion and reanchoring."""

from pathlib import Path
import pytest
from companion.equipment.schema import SlotType
from companion.equipment.baseline_cli import (
    load_baseline,
    run_baseline_refresh,
    run_baseline_set,
)
from companion.equipment.loadout_cli import (
    load_loadout,
    run_loadout_finalize,
    run_loadout_set_item,
    save_loadout,
)
from companion.equipment.engine import EquipmentIntelligenceEngine
from companion.equipment.loadout_promotion import promote_candidate_to_loadout
from companion.equipment.parser import parse_item_text
from companion.equipment.precedence import Verdict

BOOTS_INITIAL = """Item Class: Boots
Rarity: Normal
Rawhide Boots
--------
Evasion Rating: 20
--------
"""

BOOTS_CANDIDATE = """Item Class: Boots
Rarity: Rare
Loath Trail
Furtive Boots
--------
Evasion Rating: 142
Energy Shield: 29
--------
Requirements:
Level: 45
Dex: 42
Int: 42
--------
Sockets: S S
--------
Item Level: 48
--------
+66 to maximum Life
+28% to Lightning Resistance
+10% increased Movement Speed
"""


def test_uat_full_offline_workflow_lifecycle(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "offline_hero"

    # 1. Draft loadout capture
    run_loadout_set_item(runtime_dir, char_id, "boots", BOOTS_INITIAL)
    loadout = run_loadout_finalize(runtime_dir, char_id)
    assert loadout.revision == 1
    assert loadout.is_finalized is True

    # 2. Manual baseline set anchored to rev 1
    base = run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=1200,
        lightning_res=32,
        lightning_raw=32,
        max_lightning_res=75,
        dex=50,
        int=50,
    )
    assert base.anchored_loadout_revision == 1

    # 3. Candidate evaluation
    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec = engine.evaluate_candidate(BOOTS_CANDIDATE, character_id=char_id)
    assert rec.verdict == Verdict.EQUIP_NOW

    # 4. Explicit promotion
    cand = parse_item_text(BOOTS_CANDIDATE)
    new_loadout, new_base = promote_candidate_to_loadout(
        loadout=loadout,
        candidate=cand,
        slot=SlotType.BOOTS,
        baseline=base,
    )
    save_loadout(runtime_dir, new_loadout)
    assert new_loadout.revision == 2
    assert new_base.anchored_loadout_revision == 2
    assert new_base.raw_lightning_res.value == 60

    # 5. Refresh baseline reanchors directly to current revision (rev 2)
    refreshed_base = run_baseline_refresh(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=1266,
        lightning_res=60,
        lightning_raw=60,
    )
    assert refreshed_base.anchored_loadout_revision == 2
    assert refreshed_base.life.value == 1266
