"""Integration tests for PoB2 Live Helmet Advisor in live watcher."""

from pathlib import Path
import pytest

from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.live_watcher import run_live_watcher
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.equipment.pob2_helmet_advisor import Pob2HelmetSession
from companion.equipment.rules import BuildProgressionStage
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore
from tests.unit.equipment.test_pob2_helmet_advisor import (
    BRIMSTONE_VEIL_RAW,
    KRAKEN_DOME_RAW,
    FakePobEngine,
    FakePoeApi,
)

SAMPLE_BOOTS_RAW = """Item Class: Boots
Rarity: Rare
Beryl Stride
Mesh Greaves
--------
Armour: 50
--------
Requirements:
Level: 15
Str: 20
--------
Item Level: 18
--------
+25 to maximum Life
+15% to Cold Resistance
20% increased Movement Speed
"""


def _setup_runtime(tmp_path: Path, char_id: str = "test_pob_hero") -> Path:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    store = CharacterStateStore(runtime_dir)
    store.save_character(
        CharacterState(
            character_id=char_id,
            character_name="Hunter",
            build_progression={"active_stage": "lvl 15-32"},
        )
    )
    store.set_active_character(char_id)

    # Initialize loadout and baseline
    run_loadout_set_item(runtime_dir, char_id, "helmet", BRIMSTONE_VEIL_RAW)
    run_loadout_finalize(runtime_dir, char_id)
    run_baseline_set(
        runtime_dir,
        char_id,
        life=361,
        fire_res=-35,
        cold_res=-50,
        lightning_res=-43,
        chaos_res=0,
        movement_speed=10,
        strength=30,
        dexterity=30,
        intelligence=30,
    )
    return runtime_dir


def test_live_watcher_pob2_helmet_advisor_upgrade_flow(tmp_path: Path):
    """When a candidate helmet is copied, PoB2 advisor simulates and outputs Fubgun verdict."""
    runtime_dir = _setup_runtime(tmp_path)
    char_id = "test_pob_hero"

    fake_engine = FakePobEngine()
    fake_api = FakePoeApi()
    pob_session = Pob2HelmetSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=fake_api,
    )
    assert pob_session.initialize() is True

    items_to_yield = [
        KRAKEN_DOME_RAW,
    ]

    def mock_reader():
        if items_to_yield:
            return items_to_yield.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    ret = run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        pob_session=pob_session,
    )
    assert ret == 0
    full_output = "\n".join(output_lines)

    # 1. Startup Banner asserts PoB2 engine ready
    assert "PoB2 engine: READY" in full_output
    assert "Character: BOMSHAK" in full_output
    assert "Current Helmet: Brimstone Veil" in full_output
    assert "LIVE ADVICE READY" in full_output

    # 2. In-flight notification
    assert "Analyzing Kraken Dome (Helmet)..." in full_output

    # 3. Final recommendation output
    assert "🟢 EQUIP NOW" in full_output
    assert "Kraken Dome (Helmet)" in full_output
    assert "vs Brimstone Veil" in full_output
    assert "+20 Life" in full_output
    assert "+7% Lightning Res" in full_output
    assert "Resistance > Life" in full_output
    assert "Fubgun" in full_output


def test_live_watcher_pob2_same_helmet_notices_already_equipped(tmp_path: Path):
    """Copying the currently equipped helmet notifies the user without re-simulating."""
    runtime_dir = _setup_runtime(tmp_path)
    char_id = "test_pob_hero"

    fake_engine = FakePobEngine()
    fake_api = FakePoeApi()
    pob_session = Pob2HelmetSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=fake_api,
    )
    assert pob_session.initialize() is True

    items_to_yield = [
        BRIMSTONE_VEIL_RAW,
    ]

    def mock_reader():
        if items_to_yield:
            return items_to_yield.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    ret = run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        pob_session=pob_session,
    )
    assert ret == 0
    full_output = "\n".join(output_lines)

    assert "Helmet is already recorded as Current Helmet (Brimstone Veil)" in full_output


def test_live_watcher_non_helmet_uses_native_engine(tmp_path: Path):
    """Copying non-helmet items seamlessly bypasses PoB2 helmet advisor to native evaluator."""
    runtime_dir = _setup_runtime(tmp_path)
    char_id = "test_pob_hero"

    fake_engine = FakePobEngine()
    fake_api = FakePoeApi()
    pob_session = Pob2HelmetSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=fake_api,
    )
    assert pob_session.initialize() is True

    items_to_yield = [
        SAMPLE_BOOTS_RAW,
    ]

    def mock_reader():
        if items_to_yield:
            return items_to_yield.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    ret = run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        pob_session=pob_session,
    )
    assert ret == 0
    full_output = "\n".join(output_lines)

    # Did not invoke helmet advisor analysis
    assert "Analyzing Beryl Stride (Helmet)..." not in full_output
    # Native evaluation was used
    assert "Beryl Stride" in full_output


def test_live_watcher_fallback_when_pob2_unavailable(tmp_path: Path):
    """When PoB2 is unavailable, watcher prints UNAVAILABLE banner and evaluates natively."""
    runtime_dir = _setup_runtime(tmp_path)
    char_id = "test_pob_hero"

    pob_session = Pob2HelmetSession(
        character_name="BOMSHAK",
        backend_path=tmp_path / "nonexistent",
    )
    pob_session.initialize()
    assert pob_session.is_available is False

    items_to_yield = [
        KRAKEN_DOME_RAW,
    ]

    def mock_reader():
        if items_to_yield:
            return items_to_yield.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    ret = run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.LEVELING_15_32,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        pob_session=pob_session,
    )
    assert ret == 0
    full_output = "\n".join(output_lines)

    assert "PoB2 engine: UNAVAILABLE" in full_output
    # Fallback to native evaluation evaluated Kraken Dome
    assert "Kraken Dome" in full_output
