"""CLI integration tests for Milestone 8 gear auto-analysis subcommands."""

import json
from pathlib import Path
import pytest

from companion.cli import main

SAMPLE_BOOTS_TOOLTIP = """
Rarity: Rare
Storm Tread
Iron Greaves
--------
Requires Level 45, 52 Str
--------
Sockets: S S
--------
+45 to Maximum Life
+25% to Cold Resistance
30% increased Movement Speed
"""


def test_gear_status_cli(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main(["gear", "status", "--runtime", str(tmp_path), "--json"])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "slots" in data
    assert "conflicts" in data


def test_gear_audit_cli(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main([
        "gear",
        "audit",
        "--slot",
        "boots",
        "--text",
        SAMPLE_BOOTS_TOOLTIP,
        "--runtime",
        str(tmp_path),
        "--json",
    ])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["slot"] == "boots"
    assert data["verification"].lower() in ("single_source", "verified")
    assert data["item_hash"] is not None


def test_gear_compare_cli(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main([
        "gear",
        "compare",
        "--slot",
        "boots",
        "--text",
        SAMPLE_BOOTS_TOOLTIP,
        "--runtime",
        str(tmp_path),
        "--json",
    ])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "comparison" in data
    assert "advice" in data
