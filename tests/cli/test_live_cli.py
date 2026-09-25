"""CLI integration tests for 'companion gear live' MVP command."""

from pathlib import Path
from unittest.mock import patch
import pytest

from companion.cli import main
from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore

BOOTS_TEXT = """Item Class: Boots
Rarity: Normal
Iron Greaves
--------
Armour: 50
--------
"""


def test_gear_live_cli_requires_stage_if_no_persisted(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main(["gear", "live", "--runtime", str(tmp_path), "--character-id", "char_none"])
    assert code == 1
    captured = capsys.readouterr()
    assert "No progression stage specified and no persisted build stage found" in captured.err


def test_gear_live_cli_starts_with_explicit_stage(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    char_id = "test_cli_live_char"
    run_loadout_set_item(tmp_path, char_id, "boots", BOOTS_TEXT)
    run_loadout_finalize(tmp_path, char_id)
    run_baseline_set(tmp_path, char_id, life=1000, fire_res=50, fire_raw=50)

    # Mock clipboard reader to raise KeyboardInterrupt on first call
    with patch("companion.equipment.live_watcher.get_clipboard_text", side_effect=KeyboardInterrupt()):
        code = main([
            "gear",
            "live",
            "--runtime",
            str(tmp_path),
            "--character-id",
            char_id,
            "--stage",
            "lvl 15-32",
            "--no-pob",
        ])

    assert code == 0
    captured = capsys.readouterr()
    assert "PoE2 Companion LIVE" in captured.out
    assert "Stage: LEVELING_15_32" in captured.out
    assert "Loadout revision: 1" in captured.out
    assert "Baseline: READY" in captured.out
    assert "Waiting for PoE2 item clipboard..." in captured.out


def test_gear_live_cli_uses_persisted_stage(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    char_id = "test_persisted_stage_char"
    store = CharacterStateStore(tmp_path)
    state = CharacterState(
        character_id=char_id,
        character_name="PersistedHero",
        build_progression={"active_stage": "lvl 53-68", "target_build": "Fubgun"},
    )
    store.save_character(state)
    store.set_active_character(char_id)

    with patch("companion.equipment.live_watcher.get_clipboard_text", side_effect=KeyboardInterrupt()):
        code = main([
            "gear",
            "live",
            "--runtime",
            str(tmp_path),
            "--character-id",
            char_id,
            "--no-pob",
        ])

    assert code == 0
    captured = capsys.readouterr()
    assert "PoE2 Companion LIVE" in captured.out
    assert "Stage: LEVELING_53_68" in captured.out


def test_gear_live_cli_bootstrap_flag_and_warning(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    char_id = "test_cli_bootstrap"
    store = CharacterStateStore(tmp_path)
    state = CharacterState(
        character_id=char_id,
        character_name="BootstrapCLI",
        build_progression={"active_stage": "lvl 15-32"},
    )
    store.save_character(state)
    store.set_active_character(char_id)

    with patch("companion.equipment.live_watcher.get_clipboard_text", side_effect=KeyboardInterrupt()):
        code = main([
            "gear",
            "live",
            "--runtime",
            str(tmp_path),
            "--character-id",
            char_id,
            "--bootstrap",
            "--no-pob",
        ])

    assert code == 0
    captured = capsys.readouterr()
    assert "Bootstrap mode: ACTIVE" in captured.out
    assert "first item copied for an unknown slot is assumed to be CURRENT EQUIPPED" in captured.out


def test_gear_live_cli_missing_baseline_transparency(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    char_id = "test_cli_no_baseline"
    store = CharacterStateStore(tmp_path)
    state = CharacterState(
        character_id=char_id,
        character_name="NoBaseCLI",
        build_progression={"active_stage": "lvl 15-32"},
    )
    store.save_character(state)
    store.set_active_character(char_id)

    with patch("companion.equipment.live_watcher.get_clipboard_text", side_effect=KeyboardInterrupt()):
        code = main([
            "gear",
            "live",
            "--runtime",
            str(tmp_path),
            "--character-id",
            char_id,
            "--no-pob",
        ])

    assert code == 0
    captured = capsys.readouterr()
    assert "Baseline: MISSING" in captured.out
    assert "Item-to-item comparison: AVAILABLE" in captured.out
    assert "Character-context projection: LIMITED" in captured.out


def test_gear_live_cli_pob_character_configuration(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    char_id = "test_cli_pob_char"
    store = CharacterStateStore(tmp_path)
    state = CharacterState(
        character_id=char_id,
        character_name="PobCharCLI",
        build_progression={"active_stage": "lvl 15-32"},
    )
    store.save_character(state)
    store.set_active_character(char_id)

    with patch("companion.equipment.live_watcher.run_live_watcher") as mock_watcher:
        mock_watcher.return_value = 0
        code = main([
            "gear",
            "live",
            "--runtime",
            str(tmp_path),
            "--character-id",
            char_id,
            "--pob-character",
            "CustomCharacterName",
        ])
        assert code == 0
        assert mock_watcher.called
        call_kwargs = mock_watcher.call_args[1]
        assert call_kwargs.get("pob_character") == "CustomCharacterName"
        assert call_kwargs.get("pob_enabled") is True
