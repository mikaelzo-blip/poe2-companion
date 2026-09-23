"""Unit tests for companion gear baseline CLI commands."""

from pathlib import Path
import pytest
from companion.equipment.baseline import CharacterStatBaseline, BaselineSource
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.loadout_cli import save_loadout
from companion.equipment.baseline_cli import (
    load_baseline,
    save_baseline,
    run_baseline_set,
    run_baseline_show,
    run_baseline_refresh,
)


def test_baseline_cli_lifecycle(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "test_char"

    # 1. Setup finalized loadout with revision 1
    loadout = EquippedLoadout.create_draft(character_id=char_id)
    loadout.finalize(loadout_id="loadout_1")
    save_loadout(runtime_dir, loadout)

    # 2. Run baseline set
    baseline = run_baseline_set(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=1500,
        fire_res=75,
        fire_raw=115,
        max_fire_res=78,
        armour=4200,
        strength=120,
    )
    assert baseline.anchored_loadout_revision == 1
    assert baseline.life.value == 1500
    assert baseline.effective_fire_res.value == 75
    assert baseline.raw_fire_res.value == 115
    assert baseline.max_fire_res.value == 78
    assert baseline.armour.value == 4200
    assert baseline.strength.value == 120
    # Omitted stat remains UNKNOWN
    assert baseline.effective_cold_res.value is None

    # 3. Run baseline show
    shown_text = run_baseline_show(runtime_dir=runtime_dir, character_id=char_id)
    assert "Life: 1500" in shown_text
    assert "Fire Res: 75% (Raw: 115%)" in shown_text
    assert "Cold Res: UNKNOWN" in shown_text
    assert "Revision: 1" in shown_text

    # 4. Advance loadout revision to 3
    loadout.revision = 3
    save_loadout(runtime_dir, loadout)

    # 5. Run baseline refresh (reanchors to revision 3 with fresh manual values or snapshot)
    refreshed = run_baseline_refresh(
        runtime_dir=runtime_dir,
        character_id=char_id,
        life=1550,
    )
    assert refreshed.anchored_loadout_revision == 3
    assert refreshed.life.value == 1550
    assert refreshed.life.source == BaselineSource.MANUAL_USER_INPUT
