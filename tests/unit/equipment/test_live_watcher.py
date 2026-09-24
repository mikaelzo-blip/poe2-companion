"""Unit tests for PoE2 Companion MVP Live Clipboard Mode."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from companion.equipment.baseline_cli import run_baseline_refresh, run_baseline_set
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item, load_loadout
from companion.equipment.precedence import Verdict
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.live_watcher import (
    format_short_human_recommendation,
    resolve_live_stage,
    run_live_watcher,
)
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore

BOOTS_CANDIDATE = """Item Class: Boots
Rarity: Rare
Storm March
Furtive Boots
--------
Armour: 75
--------
Requirements:
Level: 25
--------
+42 to maximum Life
+21% to Lightning Resistance
+16% to Cold Resistance
+15% increased Movement Speed
"""

OLD_BOOTS = """Item Class: Boots
Rarity: Normal
The Knight-errant
Iron Greaves
--------
Armour: 68
--------
"""

BOOTS_ORDINARY_UNSUPPORTED = """Item Class: Boots
Rarity: Rare
Current Greaves
Iron Greaves
--------
Armour: 68
--------
+15% increased Light Radius
+20% increased Stun and Ailment Threshold
"""

RING_CANDIDATE = """Item Class: Rings
Rarity: Rare
Dire Band
Iron Ring
--------
Requirements:
Level: 20
--------
+35 to maximum Life
+24% to Fire Resistance
+18% to Cold Resistance
"""

BLACKHEART_RING = """Item Class: Rings
Rarity: Unique
Blackheart
Iron Ring
--------
Requirements:
Level: 4
--------
5.4 Life Regenerated per second
Adds 1 to 4 Chaos Damage to Attacks
Armour applies to Chaos Damage from Hits
Hits Intimidate Enemies for 4 Seconds
"""

ORDINARY_RING = """Item Class: Rings
Rarity: Normal
Iron Ring
Iron Ring
--------
"""


def _setup_test_environment(tmp_path: Path, char_id: str = "test_player") -> Path:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Setup character state with persisted stage
    store = CharacterStateStore(runtime_dir)
    char_state = CharacterState(
        character_id=char_id,
        character_name="TestHero",
        build_progression={"active_stage": "lvl 15-32", "target_build": "Fubgun"},
    )
    store.save_character(char_state)
    store.set_active_character(char_id)

    # Setup loadout with boots
    run_loadout_set_item(runtime_dir, char_id, "boots", OLD_BOOTS)
    run_loadout_finalize(runtime_dir, char_id)

    # Setup baseline
    run_baseline_set(
        runtime_dir,
        char_id,
        life=500,
        armour=200,
        evasion=100,
        energy_shield=0,
        fire_res=30,
        fire_raw=30,
        cold_res=20,
        cold_raw=20,
        lightning_res=15,
        lightning_raw=15,
        chaos_res=0,
        chaos_raw=0,
        movement_speed=0,
    )
    return runtime_dir


def test_stage_resolution_explicit_and_persisted(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    # Explicit stage overrides persisted
    stage_explicit = resolve_live_stage("lvl 52 swap", runtime_dir, char_id)
    assert stage_explicit == BuildProgressionStage.SWAP_52

    # None stage uses persisted runtime stage
    stage_persisted = resolve_live_stage(None, runtime_dir, char_id)
    assert stage_persisted == BuildProgressionStage.LEVELING_15_32

    # Missing persisted and missing explicit raises ValueError
    empty_runtime = tmp_path / "empty_runtime"
    with pytest.raises(ValueError, match="No progression stage specified"):
        resolve_live_stage(None, empty_runtime, "nonexistent_char")


def test_new_clipboard_item_triggers_evaluation(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    clipboard_states = ["random text", BOOTS_CANDIDATE]
    calls = []

    def mock_reader():
        if clipboard_states:
            return clipboard_states.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    ret = run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )
    assert ret == 0
    full_output = "\n".join(output_lines)
    assert "Storm March" in full_output
    assert "EQUIP NOW" in full_output or "CONDITIONAL UPGRADE" in full_output


def test_same_clipboard_item_twice_evaluates_once(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    # Same candidate twice
    clipboard_states = [BOOTS_CANDIDATE, BOOTS_CANDIDATE]

    def mock_reader():
        if clipboard_states:
            return clipboard_states.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    # Check how many times "Storm March" header was emitted
    march_evals = [line for line in output_lines if "Storm March" in line]
    assert len(march_evals) == 1


def test_non_poe_clipboard_ignored(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    clipboard_states = [
        "https://pathofexile.com",
        "Hello world from browser",
        "# Markdown heading\nsome notes",
    ]

    def mock_reader():
        if clipboard_states:
            return clipboard_states.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    # No evaluation output produced for non-poe text
    eval_headers = [line for line in output_lines if "EQUIP NOW" in line or "REJECT" in line]
    assert eval_headers == []


def test_invalid_clipboard_does_not_crash(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    clipboard_states = ["", "   ", "Item Class: Boots\nRarity: None\nIncomplete"]

    def mock_reader():
        if clipboard_states:
            return clipboard_states.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    ret = run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )
    assert ret == 0


def test_boots_automatically_compare_to_boots(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    clipboard_states = [BOOTS_CANDIDATE]

    def mock_reader():
        if clipboard_states:
            return clipboard_states.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)
    assert "vs The Knight-errant" in full_output or "The Knight-errant" in full_output


def test_ambiguous_rings_both_known(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    # Equip ring1 and ring2 in loadout
    run_loadout_set_item(runtime_dir, char_id, "ring1", ORDINARY_RING)
    run_loadout_set_item(runtime_dir, char_id, "ring2", ORDINARY_RING)
    run_baseline_refresh(runtime_dir, char_id)

    clipboard_states = [RING_CANDIDATE]

    def mock_reader():
        if clipboard_states:
            return clipboard_states.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)
    # Must show comparison for both ring1 and ring2
    assert "Ring 1" in full_output or "ring1" in full_output.lower()
    assert "Ring 2" in full_output or "ring2" in full_output.lower()


def test_ambiguous_rings_only_one_known(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    # Equip only ring1 (ring2 is unobserved)
    run_loadout_set_item(runtime_dir, char_id, "ring1", ORDINARY_RING)
    run_baseline_refresh(runtime_dir, char_id)

    clipboard_states = [RING_CANDIDATE]

    def mock_reader():
        if clipboard_states:
            return clipboard_states.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)
    assert "Ring 1" in full_output or "ring1" in full_output.lower()


def test_ambiguous_rings_neither_known(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    # Neither ring1 nor ring2 is equipped
    clipboard_states = [RING_CANDIDATE]

    def mock_reader():
        if clipboard_states:
            return clipboard_states.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)
    assert "SLOT CONTEXT UNKNOWN" in full_output or "INSUFFICIENT CONTEXT" in full_output
    assert "ring1" in full_output.lower()


def test_blackheart_unsupported_displaced_modifiers_block_equip_now_only_when_replacing_that_ring(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    # Equip Blackheart in ring1
    run_loadout_set_item(runtime_dir, char_id, "ring1", BLACKHEART_RING)
    run_baseline_refresh(runtime_dir, char_id)

    clipboard_states = [RING_CANDIDATE]

    def mock_reader():
        if clipboard_states:
            return clipboard_states.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)
    # Must NOT emit confident EQUIP_NOW
    assert "EQUIP NOW" not in full_output
    assert "INSUFFICIENT DATA" in full_output
    assert "unsupported" in full_output.lower() or "unmodeled" in full_output.lower()


def test_unrelated_blackheart_does_not_block_boots_recommendation(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    # Equip Blackheart in ring1, but we are copying BOOTS
    run_loadout_set_item(runtime_dir, char_id, "ring1", BLACKHEART_RING)
    run_baseline_refresh(runtime_dir, char_id)

    clipboard_states = [BOOTS_CANDIDATE]

    def mock_reader():
        if clipboard_states:
            return clipboard_states.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)
    # Boots evaluation should NOT be blocked by Blackheart in ring1
    assert "EQUIP NOW" in full_output


def test_ordinary_unsupported_modifiers_do_not_block_equip_now(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    # Equip boots with ordinary unsupported modifiers (light radius, stun threshold)
    run_loadout_set_item(runtime_dir, char_id, "boots", BOOTS_ORDINARY_UNSUPPORTED)
    run_baseline_refresh(runtime_dir, char_id)

    clipboard_states = [BOOTS_CANDIDATE]

    def mock_reader():
        if clipboard_states:
            return clipboard_states.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)
    # Ordinary unsupported modifiers should NOT block EQUIP_NOW
    assert "EQUIP NOW" in full_output


def test_no_loadout_mutation_from_live_inspection(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    loadout_before = load_loadout(runtime_dir, char_id)
    assert loadout_before is not None
    fp_before = loadout_before.compute_fingerprint()
    rev_before = loadout_before.revision

    clipboard_states = [BOOTS_CANDIDATE, RING_CANDIDATE]

    def mock_reader():
        if clipboard_states:
            return clipboard_states.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    loadout_after = load_loadout(runtime_dir, char_id)
    assert loadout_after is not None
    assert loadout_after.compute_fingerprint() == fp_before
    assert loadout_after.revision == rev_before


def test_keyboard_interrupt_exits_cleanly(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    def mock_reader():
        raise KeyboardInterrupt()

    output_lines = []
    ret = run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
    )
    assert ret == 0
