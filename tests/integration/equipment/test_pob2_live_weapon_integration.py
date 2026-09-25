"""Integration tests for live watcher PoB2 weapon advice using Modular Weapon Subsystems."""

from pathlib import Path
import pytest
from companion.equipment.live_watcher import run_live_watcher
from companion.equipment.loadout_cli import run_loadout_finalize, run_loadout_set_item
from companion.equipment.pob2_equipment_advisor import Pob2EquipmentSession
from companion.equipment.rules import BuildProgressionStage
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore
from tests.unit.equipment.test_pob2_helmet_advisor import FakePobEngine, FakePoeApi

CROSSBOW_PRESWAP = """Item Class: Crossbows
Rarity: Rare
Gloom Piercer
Bombard Crossbow
--------
Physical Damage: 30-75
--------
Requirements:
Level: 16
--------
+20 to maximum Life
+10% to Fire Resistance
+15% to Attack Speed
"""

STAFF_POSTSWAP = """Item Class: Two Hand Staves
Rarity: Rare
Volcano Pillar
Chiming Staff
--------
Physical Damage: 45-93
--------
Requirements:
Level: 52
--------
+20% to Fire Resistance
+2 to Level of all Fire Spell Skill Gems
Adds 15 to 30 Fire Damage to Spells
"""

BOW_TEXT = """Item Class: Bows
Rarity: Rare
Wind Bow
Short Bow
--------
Requirements:
Level: 30
--------
+10 to Dexterity
"""

CROSSBOW_FLAT_FIRE = """Item Class: Crossbows
Rarity: Rare
Infernal Crossbow
Bombard Crossbow
--------
Physical Damage: 30-75
--------
Requirements:
Level: 52
--------
Adds 10 to 20 Fire Damage to Attacks
+15% to Attack Speed
"""


def _setup_runtime(tmp_path: Path, stage: str = "lvl 15-32") -> Path:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    store = CharacterStateStore(runtime_dir)
    store.save_character(
        CharacterState(
            character_id="test_pob_hero",
            character_name="BOMSHAK",
            build_progression={"active_stage": stage},
        )
    )
    store.set_active_character("test_pob_hero")
    return runtime_dir


def test_live_watcher_preswap_crossbow_uses_pob2(tmp_path: Path):
    runtime_dir = _setup_runtime(tmp_path, stage="lvl 15-32")
    char_id = "test_pob_hero"

    fake_engine = FakePobEngine()
    fake_engine.equipped_by_slot = {
        "Weapon 1": {
            "equipped": True,
            "name": "Old Wood Crossbow",
            "raw": "Item Class: Crossbows\nRarity: Normal\nOld Wood Crossbow\n--------\n",
        }
    }
    pob_session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert pob_session.initialize() is True

    items_to_yield = [CROSSBOW_PRESWAP]

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

    assert "Analyzing Gloom Piercer" in full_output
    assert fake_engine.call_log.count("equip_item") >= 1
    assert "Fubgun" in full_output


def test_live_watcher_postswap_staff_uses_pob2_flameblast(tmp_path: Path):
    runtime_dir = _setup_runtime(tmp_path, stage="lvl 52 Swap")
    char_id = "test_pob_hero"

    fake_engine = FakePobEngine()
    fake_engine.equipped_by_slot = {
        "Weapon 1": {
            "equipped": True,
            "name": "Current Staff",
            "raw": "Item Class: Two Hand Staves\nRarity: Normal\nCurrent Staff\n--------\n",
        }
    }
    pob_session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert pob_session.initialize() is True

    items_to_yield = [STAFF_POSTSWAP]

    def mock_reader():
        if items_to_yield:
            return items_to_yield.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    ret = run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.SWAP_52,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        pob_session=pob_session,
    )
    assert ret == 0
    full_output = "\n".join(output_lines)

    assert "Analyzing Volcano Pillar" in full_output
    assert fake_engine.call_log.count("equip_item") >= 1
    assert "Flameblast" in full_output or "Weapon Set 1" in full_output


def test_live_watcher_rejects_bow_outside_fubgun_plan(tmp_path: Path):
    runtime_dir = _setup_runtime(tmp_path, stage="lvl 15-32")
    char_id = "test_pob_hero"

    fake_engine = FakePobEngine()
    pob_session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert pob_session.initialize() is True

    items_to_yield = [BOW_TEXT]

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

    assert "bow" in full_output.lower()
    # Does not simulate in PoB
    assert fake_engine.call_log.count("equip_item") == 0


def test_live_watcher_rejects_flat_fire_crossbow_postswap(tmp_path: Path):
    runtime_dir = _setup_runtime(tmp_path, stage="lvl 52 Swap")
    char_id = "test_pob_hero"

    fake_engine = FakePobEngine()
    pob_session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert pob_session.initialize() is True

    items_to_yield = [CROSSBOW_FLAT_FIRE]

    def mock_reader():
        if items_to_yield:
            return items_to_yield.pop(0)
        raise KeyboardInterrupt()

    output_lines = []
    ret = run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=BuildProgressionStage.SWAP_52,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        pob_session=pob_session,
    )
    assert ret == 0
    full_output = "\n".join(output_lines)

    assert "fire" in full_output.lower()
    # Build breaker should block PoB simulation or reject confidently
    assert "oil grenade" in full_output.lower() or "ignite" in full_output.lower() or "breaker" in full_output.lower() or "reject" in full_output.lower()
