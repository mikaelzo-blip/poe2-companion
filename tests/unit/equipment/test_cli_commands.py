"""Unit tests for companion gear CLI command routing."""

from pathlib import Path
from unittest.mock import patch
import pytest
from companion.cli import main

BOOTS_TEXT = """Item Class: Boots
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


def test_cli_gear_loadout_and_baseline_lifecycle(tmp_path: Path, capsys):
    runtime_dir = str(tmp_path / "runtime")
    char_id = "cli_char"
    item_file = tmp_path / "boots.txt"
    item_file.write_text(BOOTS_TEXT, encoding="utf-8")

    # 1. Set loadout item
    code = main(["gear", "loadout", "set-clipboard", "--slot", "boots", "--file", str(item_file), "--runtime", runtime_dir, "--character-id", char_id])
    assert code == 0

    # 2. Finalize loadout
    code = main(["gear", "loadout", "finalize", "--runtime", runtime_dir, "--character-id", char_id])
    assert code == 0

    # 3. Set baseline
    code = main(["gear", "baseline", "set", "--life", "2000", "--lightning-res", "70", "--lightning-raw", "70", "--runtime", runtime_dir, "--character-id", char_id])
    assert code == 0

    # 4. Show baseline
    code = main(["gear", "baseline", "show", "--runtime", runtime_dir, "--character-id", char_id])
    assert code == 0
    captured = capsys.readouterr()
    assert "Character Stat Baseline" in captured.out
    assert "2000" in captured.out

    # 5. Evaluate file
    code = main(["gear", "evaluate", "--file", str(item_file), "--slot", "boots", "--runtime", runtime_dir, "--character-id", char_id])
    assert code == 0
    captured = capsys.readouterr()
    assert "EQUIPMENT INTELLIGENCE EVALUATION" in captured.out

    # 6. Inspect clipboard
    with patch("companion.equipment.clipboard._read_os_clipboard", return_value=BOOTS_TEXT):
        code = main(["gear", "inspect-clipboard", "--slot", "boots", "--runtime", runtime_dir, "--character-id", char_id])
        assert code == 0
        captured = capsys.readouterr()
        assert "EQUIPMENT INTELLIGENCE EVALUATION" in captured.out
