"""Unit tests for Milestone 10 PoB2 comparator and API CLI subcommands."""

import json
import pytest
from companion.api.mock_adapter import create_mock_character
from companion.api.pob2_comparator import compare_character_with_pob2
from companion.cli import main


def test_pob2_comparator_exact_and_missing_nodes() -> None:
    char = create_mock_character(character_id="hero_1", game_version="0.1.0")
    # Target tree includes all char nodes plus 2 missing nodes
    target_nodes = list(char.passives) + ["node_extra_life", "node_extra_res"]

    res = compare_character_with_pob2(char, target_passives=target_nodes, expected_game_version="0.1.0")
    assert len(res.matched_passives) == len(char.passives)
    assert len(res.missing_passives) == 2
    assert res.patch_drift_detected is False
    assert res.completion_ratio < 1.0


def test_pob2_comparator_patch_drift_detection() -> None:
    char = create_mock_character(character_id="hero_1", game_version="0.2.0")  # Patched game!
    target_nodes = list(char.passives)

    res = compare_character_with_pob2(char, target_passives=target_nodes, expected_game_version="0.1.0")
    assert res.patch_drift_detected is True
    assert "patch drift" in res.patch_drift_warning.lower()


def test_pob2_comparator_detects_passive_tree_revision_drift() -> None:
    char = create_mock_character(character_id="hero_1", tree_revision="tree-2")
    res = compare_character_with_pob2(
        char,
        target_passives=list(char.passives),
        expected_game_version="0.1.0",
        expected_tree_revision="tree-1",
    )
    assert res.patch_drift_detected is True
    assert "tree-2" in res.patch_drift_warning
    assert "tree-1" in res.patch_drift_warning


def test_api_status_cli(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POE2_CLIENT_ID", "client-id")
    monkeypatch.setenv("POE2_ACCESS_TOKEN", "access-token")
    monkeypatch.setenv("POE2_API_URL", "http://api.pathofexile.com/character")
    code = main(["api", "status", "--json"])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "oauth_status" in data
    assert "circuit_breaker" in data
    assert data["oauth_status"] == "CONFIGURED"
    assert data["live_credentials_available"] is False


def test_api_sync_cli_blocked_returns_failure(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POE2_CLIENT_ID", raising=False)
    monkeypatch.delenv("POE2_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("POE2_API_URL", raising=False)
    code = main(["api", "sync", "--json"])
    assert code == 1
    assert json.loads(capsys.readouterr().out)["character"] is None


def test_api_status_cli_without_credentials(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POE2_CLIENT_ID", raising=False)
    monkeypatch.delenv("POE2_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("POE2_API_URL", raising=False)
    code = main(["api", "status", "--json"])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "oauth_status" in data
    assert "circuit_breaker" in data
    assert data["oauth_status"] == "EXTERNALLY_BLOCKED"
    assert data["live_credentials_available"] is False


def test_api_sync_cli_mock(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["api", "sync", "--mock", "--json"])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "character" in data
    assert data["status"] == "SYNC_SUCCESS"
    assert data["character"]["level"] == 70
