"""Unit tests for companion gear evaluate --file CLI command."""

from pathlib import Path
import pytest
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.clipboard import run_evaluate_file

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


def test_cli_evaluate_file(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "test_eval_char"

    item_file = tmp_path / "boots.txt"
    item_file.write_text(BOOTS_ITEM, encoding="utf-8")

    run_loadout_set_item(
        runtime_dir,
        char_id,
        "boots",
        """Item Class: Boots
Rarity: Normal
Iron Greaves
--------
""",
    )
    run_loadout_finalize(runtime_dir, char_id)
    run_baseline_set(
        runtime_dir,
        char_id,
        life=2000,
        fire_res=75,
        fire_raw=75,
        cold_res=75,
        cold_raw=75,
        lightning_res=70,
        lightning_raw=70,
        chaos_res=0,
        chaos_raw=0,
        movement_speed=0,
    )

    report, rec = run_evaluate_file(
        runtime_dir=runtime_dir,
        file_path=item_file,
        character_id=char_id,
        slot_name="boots",
    )

    assert "EQUIP_NOW" in report
    assert rec.candidate.name == "Loath Trail"
