"""CLI integration tests for Milestone 9 expanded intelligence subcommands."""

import json
from pathlib import Path
import pytest
from companion.cli import main


def test_intelligence_story_cli(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["intelligence", "story", "--json"])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["status"] == "DEFERRED_BY_BLUEPRINT"
    assert data["feature"] == "story_progression"
    assert "62" in data["blueprint_section"]


def test_intelligence_economy_cli(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["intelligence", "economy", "--level", "60", "--json"])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["status"] == "DEFERRED_BY_BLUEPRINT"
    assert data["feature"] == "economy_prioritization"
    assert "62" in data["blueprint_section"]


def test_intelligence_audit_cli(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main(["intelligence", "audit", "--runtime", str(tmp_path), "--level", "70", "--json"])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "advisories" in data
    assert isinstance(data["advisories"], list)
