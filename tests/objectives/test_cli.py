"""Unit and integration tests for M4 CLI commands: objectives and evaluate."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from companion.cli import main
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore


@pytest.fixture
def populated_runtime(tmp_path: Path) -> tuple[Path, CharacterState]:
    runtime_dir = tmp_path / "runtime"
    store = CharacterStateStore(runtime_dir)
    char = CharacterState.create_initial(
        character_id="test_m4_hero",
        character_name="TestM4Hero",
    )
    store.save_character(char)
    store.set_active_character(char.character_id)
    return runtime_dir, char


def test_objectives_list_human_readable(populated_runtime: tuple[Path, CharacterState], capsys: pytest.CaptureFixture[str]) -> None:
    runtime_dir, _ = populated_runtime
    exit_code = main(["objectives", "list", "--runtime", str(runtime_dir)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "DO NOW:" in captured.out or "NO_ACTIONABLE_OBJECTIVE" in captured.out


def test_objectives_list_json(populated_runtime: tuple[Path, CharacterState], capsys: pytest.CaptureFixture[str]) -> None:
    runtime_dir, _ = populated_runtime
    exit_code = main(["objectives", "list", "--runtime", str(runtime_dir), "--json"])
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "all_objectives" in data
    assert "status" in data


def test_objectives_next_human_readable(populated_runtime: tuple[Path, CharacterState], capsys: pytest.CaptureFixture[str]) -> None:
    runtime_dir, _ = populated_runtime
    exit_code = main(["objectives", "next", "--runtime", str(runtime_dir)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "DO NOW:" in captured.out or "NO_ACTIONABLE_OBJECTIVE" in captured.out


def test_objectives_next_json(populated_runtime: tuple[Path, CharacterState], capsys: pytest.CaptureFixture[str]) -> None:
    runtime_dir, _ = populated_runtime
    exit_code = main(["objectives", "next", "--runtime", str(runtime_dir), "--json"])
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "id" in data or "status" in data


def test_evaluate_command_generates_current_objective_artifact(
    populated_runtime: tuple[Path, CharacterState],
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime_dir, char = populated_runtime
    char_file = runtime_dir / "characters" / f"{char.character_id}.json"
    out_artifact = runtime_dir / "CURRENT_OBJECTIVE.json"

    exit_code = main(["evaluate", str(char_file), "--out", str(out_artifact), "--runtime", str(runtime_dir)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "DO NOW:" in captured.out or "NO_ACTIONABLE_OBJECTIVE" in captured.out
    assert out_artifact.is_file()

    saved_data = json.loads(out_artifact.read_text(encoding="utf-8"))
    assert saved_data["character_id"] == char.character_id
    assert "status" in saved_data


def test_evaluate_missing_character_file_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing_file = tmp_path / "non_existent.json"
    exit_code = main(["evaluate", str(missing_file)])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "not found" in captured.err.lower() or "error" in captured.err.lower()
