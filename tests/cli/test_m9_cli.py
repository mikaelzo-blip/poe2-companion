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
    assert "quests" in data
    assert len(data["quests"]) >= 4
    assert any("Spirit" in q["reward_type"] or "SPIRIT" in q["reward_type"] for q in data["quests"])


def test_intelligence_economy_cli(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["intelligence", "economy", "--level", "60", "--json"])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "priorities" in data
    assert len(data["priorities"]) >= 2
    assert data["priorities"][0]["priority_tier"] == 1


def test_intelligence_audit_cli(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main(["intelligence", "audit", "--runtime", str(tmp_path), "--level", "70", "--json"])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "advisories" in data
    assert isinstance(data["advisories"], list)
