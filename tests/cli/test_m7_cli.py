"""Unit and integration tests for M7 CLI subcommands: vision status and parse-panel."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from companion.cli import main


def test_vision_status_cli(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["vision", "status", "--json"])
    assert exit_code == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert "budget" in data
    assert "privacy" in data
    assert data["budget"]["enabled"] is True


def test_vision_parse_panel_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    panel_file = tmp_path / "panel.txt"
    panel_file.write_text(
        "Character\n"
        "Maximum Life: 1,200\n"
        "Maximum Mana: 350\n"
        "Fire Resistance: 75%\n"
        "Cold Resistance: 60%\n"
        "Lightning Resistance: 75%\n"
        "Chaos Resistance: -10%\n",
        encoding="utf-8",
    )

    exit_code = main([
        "vision", "parse-panel",
        "--file", str(panel_file),
        "--json",
    ])
    assert exit_code == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["screen_type"] == "CHARACTER_PANEL"
    assert data["stats"]["life"] == 1200
    assert data["stats"]["fire_res"] == 75
    assert data["verification_state"] == "SINGLE_SOURCE"
