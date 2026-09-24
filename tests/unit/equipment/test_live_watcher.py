"""Unit tests for PoE2 Companion MVP Live Clipboard Mode."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from companion.equipment.baseline_cli import run_baseline_refresh, run_baseline_set
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item, load_loadout
from companion.equipment.precedence import Verdict
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.equipment.live_watcher import (
    format_short_human_recommendation,
    resolve_live_stage,
    run_live_watcher,
    supports_color,
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


SECOND_RING = """Item Class: Rings
Rarity: Rare
Loath Band
Gold Ring
--------
Requirements:
Level: 16
--------
+25 to maximum Life
+15% to Cold Resistance
"""

STAFF_TEXT = """Item Class: Staves
Rarity: Rare
Gloom Branch
Quarterstaff
--------
Requirements:
Level: 20
--------
+15% to Fire Resistance
+20 to maximum Life
"""

CROSSBOW_TEXT = """Item Class: Crossbows
Rarity: Rare
Doom Bolt
Bombard Crossbow
--------
Requirements:
Level: 25
--------
+25 to maximum Life
+15% to Cold Resistance
"""

BOOTS_WITH_RES = """Item Class: Boots
Rarity: Magic
Fleet Iron Greaves
Iron Greaves
--------
Armour: 68
--------
+25% to Fire Resistance
"""

BOOTS_WITH_LIFE = """Item Class: Boots
Rarity: Magic
Stout Iron Greaves
Iron Greaves
--------
Armour: 75
--------
+40 to maximum Life
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


def test_bootstrap_banner_warns_first_item_assumed_equipped(tmp_path: Path):
    runtime_dir = _setup_test_environment(tmp_path)
    char_id = "test_player"

    def mock_reader():
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        bootstrap=True,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
    )
    full_output = "\n".join(output_lines)
    assert "Bootstrap mode: ACTIVE" in full_output
    assert "first item copied for an unknown slot is assumed to be CURRENT EQUIPPED" in full_output
    assert "Copy CURRENT Weapon Set 1 first, then CURRENT Weapon Set 2." in full_output


def test_live_watcher_missing_baseline_banner_display(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_id = "test_no_baseline"

    # Store character state with stage, but NO baseline
    store = CharacterStateStore(runtime_dir)
    char_state = CharacterState(
        character_id=char_id,
        character_name="NoBaselineHero",
        build_progression={"active_stage": "lvl 15-32"},
    )
    store.save_character(char_state)
    store.set_active_character(char_id)

    def mock_reader():
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
    )
    full_output = "\n".join(output_lines)
    assert "Baseline: MISSING" in full_output
    assert "Item-to-item comparison: AVAILABLE" in full_output
    assert "Character-context projection: LIMITED" in full_output


def test_live_bootstrap_no_restart_flow_single_slot(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_id = "test_bootstrap_char"

    store = CharacterStateStore(runtime_dir)
    char_state = CharacterState(
        character_id=char_id,
        character_name="BootstrapHero",
        build_progression={"active_stage": "lvl 15-32"},
    )
    store.save_character(char_state)
    store.set_active_character(char_id)

    # Empty loadout at start (no boots)
    loadout_init = load_loadout(runtime_dir, char_id)
    assert loadout_init.get_slot(SlotType.BOOTS) is None

    # Sequential clipboard states: 1. Current boots, 2. Candidate boots
    clipboard_items = [OLD_BOOTS, BOOTS_CANDIDATE]

    def mock_reader():
        if clipboard_items:
            return clipboard_items.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        bootstrap=True,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)

    # 1. Learned current boots
    assert "✓ CURRENT BOOTS LEARNED" in full_output
    assert "The Knight-errant" in full_output

    # 2. Immediately evaluated candidate against The Knight-errant in the same running watcher
    assert "Storm March" in full_output
    assert "vs The Knight-errant" in full_output

    # 3. Loadout persisted The Knight-errant as equipped boots
    loadout_persisted = load_loadout(runtime_dir, char_id)
    boots_entry = loadout_persisted.get_slot(SlotType.BOOTS)
    assert boots_entry is not None
    assert boots_entry.item is not None
    assert boots_entry.item.name == "The Knight-errant"


def test_live_bootstrap_rings_flow(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_id = "test_bootstrap_rings"

    store = CharacterStateStore(runtime_dir)
    char_state = CharacterState(
        character_id=char_id,
        character_name="RingHero",
        build_progression={"active_stage": "lvl 15-32"},
    )
    store.save_character(char_state)
    store.set_active_character(char_id)

    # Sequence: 1. Ring 1 (Iron Ring), 2. Ring 2 (Loath Band), 3. Candidate (Dire Band)
    clipboard_items = [ORDINARY_RING, SECOND_RING, RING_CANDIDATE]

    def mock_reader():
        if clipboard_items:
            return clipboard_items.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        bootstrap=True,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)

    # First ring learned as Ring 1
    assert "✓ CURRENT RING 1 LEARNED" in full_output
    assert "Iron Ring" in full_output

    # Second distinct ring learned as Ring 2
    assert "✓ CURRENT RING 2 LEARNED" in full_output
    assert "Loath Band" in full_output

    # Third ring evaluated as candidate against both rings
    assert "Dire Band" in full_output
    assert "Ring 1" in full_output or "vs Iron Ring" in full_output
    assert "Ring 2" in full_output or "vs Loath Band" in full_output

    # Loadout check
    loadout = load_loadout(runtime_dir, char_id)
    r1 = loadout.get_slot(SlotType.RING_1)
    r2 = loadout.get_slot(SlotType.RING_2)
    assert r1 is not None and r1.item is not None
    assert r1.item.base_type == "Iron Ring"
    assert r2 is not None and r2.item is not None
    assert r2.item.name == "Loath Band"


def test_live_bootstrap_duplicate_ring_not_learned_as_ring2(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_id = "test_dup_ring"

    store = CharacterStateStore(runtime_dir)
    store.save_character(CharacterState(character_id=char_id, character_name="DupHero", build_progression={"active_stage": "lvl 15-32"}))
    store.set_active_character(char_id)

    # User copies Iron Ring, then copies another item, then copies same Iron Ring again
    clipboard_items = [ORDINARY_RING, BOOTS_CANDIDATE, ORDINARY_RING]

    def mock_reader():
        if clipboard_items:
            return clipboard_items.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        bootstrap=True,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)
    assert "✓ CURRENT RING 1 LEARNED" in full_output
    assert "✓ CURRENT RING 2 LEARNED" not in full_output

    loadout = load_loadout(runtime_dir, char_id)
    assert loadout.get_slot(SlotType.RING_2) is None


def test_live_normal_mode_weapon_set_ambiguity_guard(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_id = "test_weapon_guard"

    store = CharacterStateStore(runtime_dir)
    store.save_character(CharacterState(character_id=char_id, character_name="WeaponHero", build_progression={"active_stage": "lvl 15-32"}))
    store.set_active_character(char_id)

    # 1. Weapon copied in normal mode (bootstrap=False) without --weapon-set -> must NOT blindly equip
    clipboard_items = [STAFF_TEXT]

    def mock_reader():
        if clipboard_items:
            return clipboard_items.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        bootstrap=False,
        weapon_set=None,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)
    assert "WEAPON SET CONTEXT AMBIGUOUS" in full_output or "--weapon-set" in full_output

    loadout = load_loadout(runtime_dir, char_id)
    assert loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_1) is None
    assert loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_2) is None


def test_live_bootstrap_weapons_sequential_flow(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_id = "test_bootstrap_weapons"

    store = CharacterStateStore(runtime_dir)
    store.save_character(CharacterState(character_id=char_id, character_name="WeaponSeqHero", build_progression={"active_stage": "lvl 52 Swap"}))
    store.set_active_character(char_id)

    # Sequence: 1. Staff (Set 1), 2. Interleaved Boots, 3. Duplicate Staff, 4. Crossbow (Set 2)
    clipboard_items = [STAFF_TEXT, BOOTS_CANDIDATE, STAFF_TEXT, CROSSBOW_TEXT]

    def mock_reader():
        if clipboard_items:
            return clipboard_items.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.SWAP_52,
        bootstrap=True,
        weapon_set=None,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)
    # Check instructions and sequential learning
    assert "Copy CURRENT Weapon Set 1 first, then CURRENT Weapon Set 2." in full_output
    assert "✓ CURRENT WEAPON SET 1 LEARNED" in full_output
    assert "Gloom Branch" in full_output
    assert "Weapon is already recorded as Weapon Set 1" in full_output
    assert "✓ CURRENT WEAPON SET 2 LEARNED" in full_output
    assert "Doom Bolt" in full_output

    loadout = load_loadout(runtime_dir, char_id)
    w1 = loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_1)
    w2 = loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_2)
    assert w1 is not None and w1.item is not None
    assert w1.item.name == "Gloom Branch"
    assert w2 is not None and w2.item is not None
    assert w2.item.name == "Doom Bolt"
    # Staff is two-handed, so off_hand in Set 1 must be None
    assert loadout.get_slot(SlotType.OFF_HAND, weapon_set=WeaponSetContext.WEAPON_SET_1) is None


def test_live_watcher_color_formatting(monkeypatch, tmp_path):
    from companion.equipment.engine import EquipmentIntelligenceEngine
    from companion.equipment.rules import BuildProgressionStage

    # 1. Test supports_color
    monkeypatch.setenv("NO_COLOR", "1")
    assert supports_color() is False

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert supports_color() is True

    # 2. Test format_short_human_recommendation with use_color=True
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    run_loadout_set_item(runtime_dir, "color_char", "boots", OLD_BOOTS)
    run_loadout_finalize(runtime_dir, "color_char")
    run_baseline_set(
        runtime_dir,
        "color_char",
        life=1000,
        fire_res=50,
        cold_res=50,
        lightning_res=50,
        chaos_res=0,
        strength=50,
        dexterity=50,
        intelligence=50,
        movement_speed=0,
        armour=100,
        evasion=100,
    )
    engine = EquipmentIntelligenceEngine(runtime_dir=runtime_dir)
    rec_equip = engine.evaluate_candidate(
        item_text=BOOTS_CANDIDATE,
        character_id="color_char",
        target_slot=SlotType.BOOTS,
        stage=BuildProgressionStage.LEVELING_15_32,
    )

    out_colored = format_short_human_recommendation(rec_equip, use_color=True)
    assert "\033[32m" in out_colored

    # 3. Test plain formatting with use_color=False
    out_plain = format_short_human_recommendation(rec_equip, use_color=False)
    assert "\033[" not in out_plain
    assert "INSUFFICIENT DATA" in out_plain or "EQUIP NOW" in out_plain or "REJECT" in out_plain


def test_normal_mode_does_not_bootstrap_unknown_slot(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_id = "test_normal_mode"

    store = CharacterStateStore(runtime_dir)
    store.save_character(CharacterState(character_id=char_id, character_name="NormalHero", build_progression={"active_stage": "lvl 15-32"}))
    store.set_active_character(char_id)

    # Empty loadout, normal mode (bootstrap=False)
    clipboard_items = [OLD_BOOTS]

    def mock_reader():
        if clipboard_items:
            return clipboard_items.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        bootstrap=False,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)
    assert "✓ CURRENT BOOTS LEARNED" not in full_output
    assert "INSUFFICIENT DATA" in full_output or "unobserved" in full_output

    loadout = load_loadout(runtime_dir, char_id)
    assert loadout.get_slot(SlotType.BOOTS) is None


def test_missing_baseline_reports_directly_known_deltas(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_id = "test_deltas_no_baseline"

    store = CharacterStateStore(runtime_dir)
    store.save_character(CharacterState(character_id=char_id, character_name="DeltaHero", build_progression={"active_stage": "lvl 15-32"}))
    store.set_active_character(char_id)

    # Setup loadout with BOOTS_WITH_RES, NO baseline on disk
    run_loadout_set_item(runtime_dir, char_id, "boots", BOOTS_WITH_RES)

    # Candidate has +40 Life, but loses 25% Fire Res -> trade-off without baseline -> INSUFFICIENT DATA
    clipboard_items = [BOOTS_WITH_LIFE]

    def mock_reader():
        if clipboard_items:
            return clipboard_items.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        bootstrap=False,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)
    # Verdict must be INSUFFICIENT DATA because of resistance loss without baseline
    assert "INSUFFICIENT DATA" in full_output
    # Directly known item deltas MUST be reported
    assert "+40 Life" in full_output
    assert "25% Fire Res" in full_output
    # Must NOT fabricate absolute projection (no arrows like 30% -> 5%)
    assert "→" not in full_output
