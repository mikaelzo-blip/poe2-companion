"""Unit tests for complete offline equipment intelligence workflow."""

from pathlib import Path
import pytest
from companion.equipment.schema import SlotType
from companion.equipment.loadout_cli import (
    run_loadout_set_item,
    run_loadout_finalize,
    load_loadout,
)
from companion.equipment.baseline_cli import (
    run_baseline_set,
    load_baseline,
)
from companion.equipment.clipboard import run_evaluate_file
from companion.equipment.loadout_promotion import promote_candidate_to_loadout
from companion.equipment.loadout_cli import save_loadout
from companion.equipment.baseline_cli import save_baseline

OLD_BOOTS = """Item Class: Boots
Rarity: Rare
Old Treads
Furtive Boots
--------
Requirements:
Level: 45
--------
+30 to maximum Life
+10% to Fire Resistance
"""

NEW_BOOTS = """Item Class: Boots
Rarity: Rare
Fleet Steps
Furtive Boots
--------
Requirements:
Level: 45
--------
+70 to maximum Life
+30% to Fire Resistance
+20% increased Movement Speed
"""


def test_complete_offline_workflow(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "fubgun_offline"

    # Step 1: Ingest existing boots manually to draft loadout
    run_loadout_set_item(runtime_dir, char_id, "boots", OLD_BOOTS)

    # Step 2: Finalize loadout (starts revision 1)
    loadout = run_loadout_finalize(runtime_dir, char_id, loadout_id="fubgun_starter")
    assert loadout.revision == 1
    assert loadout.is_finalized is True

    # Step 3: Set manual baseline anchored to revision 1
    baseline = run_baseline_set(
        runtime_dir,
        char_id,
        life=2500,
        fire_res=70,
        fire_raw=70,
        movement_speed=10,
    )
    assert baseline.anchored_loadout_revision == 1

    # Step 4: Evaluate candidate from file
    cand_file = tmp_path / "new_boots.txt"
    cand_file.write_text(NEW_BOOTS, encoding="utf-8")

    report, rec = run_evaluate_file(
        runtime_dir=runtime_dir,
        file_path=cand_file,
        character_id=char_id,
        slot_name="boots",
    )
    assert "EQUIP_NOW" in report

    # Verify inspection did not mutate revision!
    loadout_check = load_loadout(runtime_dir, char_id)
    assert loadout_check.revision == 1

    # Step 5: Promote candidate to loadout
    new_loadout, new_baseline = promote_candidate_to_loadout(
        loadout=loadout_check,
        candidate=rec.candidate,
        slot=SlotType.BOOTS,
        baseline=baseline,
    )
    assert new_loadout.revision == 2
    assert new_baseline.anchored_loadout_revision == 2
    # Fire res rebased: 70 + (30 - 10) = 90 raw, effective 75, overcap 15
    assert new_baseline.effective_fire_res.value == 75
    assert new_baseline.raw_fire_res.value == 90
    assert new_baseline.fire_overcap_buffer.value == 15

    # Step 6: Persist updated loadout and baseline
    save_loadout(runtime_dir, new_loadout)
    save_baseline(runtime_dir, new_baseline)

    # Step 7: Reload to prove persistence
    reloaded_loadout = load_loadout(runtime_dir, char_id)
    reloaded_baseline = load_baseline(runtime_dir, char_id)

    assert reloaded_loadout.revision == 2
    assert reloaded_loadout.get_slot(SlotType.BOOTS).item.name == "Fleet Steps"
    assert reloaded_baseline.anchored_loadout_revision == 2
    assert reloaded_baseline.effective_fire_res.value == 75
