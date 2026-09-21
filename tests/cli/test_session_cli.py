"""Unit and integration tests for M5 CLI commands: session and journey."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from companion.cli import main
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore


@pytest.fixture
def session_env(tmp_path: Path) -> tuple[Path, Path, CharacterState]:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    store = CharacterStateStore(runtime_dir)

    char = CharacterState.create_initial("hero_session", "HeroSession")
    store.save_character(char)
    store.set_active_character("hero_session")

    log_file = tmp_path / "Client.txt"
    log_file.write_text(
        "2026/09/22 12:00:00 123 [INFO Client 1] : Entered area \"Omen Ridge\"\n"
        "2026/09/22 12:05:00 123 [INFO Client 1] : HeroSession is now level 15\n",
        encoding="utf-8",
    )
    return runtime_dir, log_file, char


def test_session_status_cli(session_env: tuple[Path, Path, CharacterState], capsys: pytest.CaptureFixture[str]) -> None:
    runtime_dir, _, _ = session_env
    exit_code = main(["session", "status", "--runtime", str(runtime_dir)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "HeroSession" in captured.out or "hero_session" in captured.out


def test_session_status_json_cli(session_env: tuple[Path, Path, CharacterState], capsys: pytest.CaptureFixture[str]) -> None:
    runtime_dir, _, _ = session_env
    exit_code = main(["session", "status", "--runtime", str(runtime_dir), "--json"])
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["character_id"] == "hero_session"
    assert "process_state" in data


def test_session_tail_once_reconciles_state(session_env: tuple[Path, Path, CharacterState], capsys: pytest.CaptureFixture[str]) -> None:
    runtime_dir, log_file, _ = session_env
    exit_code = main([
        "session", "tail",
        "--log", str(log_file),
        "--runtime", str(runtime_dir),
        "--once",
    ])
    assert exit_code == 0
    store = CharacterStateStore(runtime_dir)
    updated = store.load_character("hero_session")
    assert updated is not None
    assert updated.current_zone.value == "Omen Ridge"
    assert updated.level.value == 15


def test_journey_list_cli(session_env: tuple[Path, Path, CharacterState], capsys: pytest.CaptureFixture[str]) -> None:
    runtime_dir, log_file, _ = session_env
    # Run tail once to generate journey history entries
    main([
        "session", "tail",
        "--log", str(log_file),
        "--runtime", str(runtime_dir),
        "--once",
    ])
    capsys.readouterr()  # Flush tail stdout

    exit_code = main(["journey", "list", "--runtime", str(runtime_dir), "--json"])
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["event_type"] == "zone_transition"
    assert data[1]["event_type"] == "level_up"
