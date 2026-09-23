"""Unit tests for companion gear inspect-clipboard CLI command."""

from pathlib import Path
from unittest.mock import patch
import pytest
from companion.equipment.loadout_cli import run_loadout_set_item, run_loadout_finalize
from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.clipboard import run_inspect_clipboard

BOOTS_ITEM = """Item Class: Boots
Rarity: Rare
Loath Trail
Furtive Boots
--------
Requirements:
Level: 45
--------
+66 to maximum Life
+28% to Lightning Resistance
+10% increased Movement Speed
"""


def test_cli_inspect_clipboard(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "test_clip_char"

    # Setup baseline and loadout
    run_loadout_finalize(runtime_dir, char_id)
    run_baseline_set(runtime_dir, char_id, life=2000, lightning_res=70, lightning_raw=70)

    with patch("companion.equipment.clipboard._read_os_clipboard", return_value=BOOTS_ITEM):
        report, rec = run_inspect_clipboard(
            runtime_dir=runtime_dir,
            character_id=char_id,
            slot_name="boots",
        )

    assert "EQUIP_NOW" in report
    assert rec.candidate.name == "Loath Trail"
