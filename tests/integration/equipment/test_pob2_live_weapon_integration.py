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


SAMPLE_HELMET_RAW = """Item Class: Helmets
Rarity: Rare
Kraken Dome
Soldier Greathelm
--------
Armour: 45
--------
Requirements:
Level: 15
--------
+20 to maximum Life
+7% to Lightning Resistance
"""

SAMPLE_BODY_ARMOUR_RAW = """Item Class: Body Armours
Rarity: Rare
Obsidian Plate
Plate Vest
--------
Armour: 120
--------
Requirements:
Level: 15
--------
+40 to maximum Life
+15% to Fire Resistance
"""

SAMPLE_GLOVES_RAW = """Item Class: Gloves
Rarity: Rare
Bramble Mitts
Cloth Gloves
--------
Armour: 30
--------
Requirements:
Level: 15
--------
+30 to maximum Life
+20% to Fire Resistance
"""

SAMPLE_BOOTS_RAW = """Item Class: Boots
Rarity: Rare
Beryl Stride
Mesh Greaves
--------
Armour: 50
--------
Requirements:
Level: 15
--------
+25 to maximum Life
+15% to Cold Resistance
20% increased Movement Speed
"""

SAMPLE_BELT_RAW = """Item Class: Belts
Rarity: Rare
Vigour Clasp
Chain Belt
--------
Requirements:
Level: 15
--------
+35 to maximum Life
+18% to Lightning Resistance
"""

SAMPLE_AMULET_RAW = """Item Class: Amulets
Rarity: Rare
Torment Gorget
Coral Amulet
--------
Requirements:
Level: 15
--------
+20 to maximum Life
+12% to Fire Resistance
"""

SAMPLE_RING_RAW = """Item Class: Rings
Rarity: Rare
Storm Loop
Iron Ring
--------
Requirements:
Level: 15
--------
+25 to maximum Life
+15% to Cold Resistance
"""


def test_live_watcher_e2e_session_a_preswap_full_equipment_suite(tmp_path: Path):
    """SESSION A E2E Clarification: Real pre-swap BOMSHAK lvl 17 (LEVELING_15_32).

    Validates through the actual production watcher:
    - Helmet
    - Body Armour
    - Gloves
    - Boots
    - Belt
    - Amulet
    - Ring 1 / Ring 2 (dual placement evaluation)
    - Crossbow -> Weapon Set 1 / CROSSBOW_LEVELING

    Explicitly proves that a pre-swap Crossbow does NOT route to
    Weapon Set 2 / Oil Grenade, and that Staves are rejected during pre-swap.
    """
    runtime_dir = _setup_runtime(tmp_path, stage="lvl 15-32")
    char_id = "test_pob_hero"

    fake_engine = FakePobEngine()
    fake_engine.equipped_by_slot = {
        "Helmet": {"equipped": True, "name": "Brimstone Veil", "raw": "Item Class: Helmets\nRarity: Normal\nBrimstone Veil\n--------\n"},
        "Body Armour": {"equipped": True, "name": "Plate Vest", "raw": "Item Class: Body Armours\nRarity: Normal\nPlate Vest\n--------\n"},
        "Gloves": {"equipped": True, "name": "Cloth Gloves", "raw": "Item Class: Gloves\nRarity: Normal\nCloth Gloves\n--------\n"},
        "Boots": {"equipped": True, "name": "Rawhide Boots", "raw": "Item Class: Boots\nRarity: Normal\nRawhide Boots\n--------\n"},
        "Belt": {"equipped": True, "name": "Chain Belt", "raw": "Item Class: Belts\nRarity: Normal\nChain Belt\n--------\n"},
        "Amulet": {"equipped": True, "name": "Coral Amulet", "raw": "Item Class: Amulets\nRarity: Normal\nCoral Amulet\n--------\n"},
        "Ring 1": {"equipped": True, "name": "Gloom Band", "raw": "Item Class: Rings\nRarity: Normal\nGloom Band\n--------\n"},
        "Ring 2": {"equipped": True, "name": "Blood Coil", "raw": "Item Class: Rings\nRarity: Normal\nBlood Coil\n--------\n"},
        "Weapon 1": {"equipped": True, "name": "Old Wood Crossbow", "raw": "Item Class: Crossbows\nRarity: Normal\nOld Wood Crossbow\n--------\n"},
        "Weapon 2": {"equipped": False, "name": None, "raw": None},
        "Weapon 1 Swap": {"equipped": False, "name": None, "raw": None},
        "Weapon 2 Swap": {"equipped": False, "name": None, "raw": None},
    }
    pob_session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert pob_session.initialize() is True

    items_to_yield = [
        SAMPLE_HELMET_RAW,
        SAMPLE_BODY_ARMOUR_RAW,
        SAMPLE_GLOVES_RAW,
        SAMPLE_BOOTS_RAW,
        SAMPLE_BELT_RAW,
        SAMPLE_AMULET_RAW,
        SAMPLE_RING_RAW,
        CROSSBOW_PRESWAP,
        STAFF_POSTSWAP,
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

    # 1. Core armor and jewelry slots evaluate with PoB2 advisor
    assert "Analyzing Kraken Dome (Helmet)..." in full_output
    assert "Analyzing Obsidian Plate (Body Armour)..." in full_output
    assert "Analyzing Bramble Mitts (Gloves)..." in full_output
    assert "Analyzing Beryl Stride (Boots)..." in full_output
    assert "Analyzing Vigour Clasp (Belt)..." in full_output
    assert "Analyzing Torment Gorget (Amulet)..." in full_output

    # 2. Ring evaluates with dual-ring policy vs Ring 1 and Ring 2
    assert "Analyzing Storm Loop (Rings)..." in full_output
    assert "Vs Ring 1: Gloom Band" in full_output
    assert "Vs Ring 2: Blood Coil" in full_output

    # 3. Crossbow evaluates strictly against Weapon Set 1 with CROSSBOW_LEVELING
    assert "Analyzing Gloom Piercer (Weapon 1)..." in full_output
    assert "Weapon 1 [CROSSBOW_LEVELING]" in full_output

    # 4. Explicit proof: Pre-swap Crossbow does NOT route to Weapon Set 2 or Oil Grenade
    assert "Weapon 1 Swap" not in full_output
    assert "Oil Grenade" not in full_output
    assert "Weapon Set 2" not in full_output

    # 5. Pre-swap Staves are rejected as incompatible
    assert "Staves are used post-swap (level 52+) for Flameblast; use a Crossbow during leveling." in full_output


def test_live_watcher_e2e_session_b_postswap_dual_weapon_contract(tmp_path: Path):
    """SESSION B E2E Clarification: Headless Post-Swap context (SWAP_52).

    Validates:
    - Staff -> Weapon Set 1 / Flameblast
    - Crossbow -> Weapon Set 2 / Oil Grenade
    - harmful added/flat Fire Crossbow -> immediate build breaker (blocks simulation)
    - Staff does not receive Oil Grenade breaker
    """
    runtime_dir = _setup_runtime(tmp_path, stage="lvl 52 Swap")
    char_id = "test_pob_hero"

    fake_engine = FakePobEngine()
    fake_engine.equipped_by_slot = {
        "Weapon 1": {"equipped": True, "name": "Current Staff", "raw": "Item Class: Two Hand Staves\nRarity: Normal\nCurrent Staff\n--------\n"},
        "Weapon 1 Swap": {"equipped": True, "name": "Current Crossbow", "raw": "Item Class: Crossbows\nRarity: Normal\nCurrent Crossbow\n--------\n"},
    }
    pob_session = Pob2EquipmentSession(
        character_name="BOMSHAK",
        engine_factory=lambda: fake_engine,
        poe_api_client=FakePoeApi(),
    )
    assert pob_session.initialize() is True

    items_to_yield = [
        STAFF_POSTSWAP,
        CROSSBOW_PRESWAP,  # safe crossbow (no fire damage)
        CROSSBOW_FLAT_FIRE,  # harmful flat fire crossbow
    ]

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

    # 1. Staff routes to Weapon Set 1 and uses Flameblast skill context
    assert "Analyzing Volcano Pillar (Weapon 1)..." in full_output
    assert "Weapon 1 [Flameblast]" in full_output
    # Staff has Fire Damage to Spells, but does NOT receive Oil Grenade breaker
    assert "BUILD BREAKER" not in full_output.split("Analyzing Volcano Pillar")[1].split("Analyzing Gloom Piercer")[0]

    # 2. Safe Crossbow routes to Weapon Set 2 and uses Oil Grenade skill context
    assert "Analyzing Gloom Piercer (Weapon 1 Swap)..." in full_output
    assert "Weapon 1 Swap [Oil Grenade]" in full_output

    # 3. Harmful flat fire Crossbow triggers immediate build breaker
    assert "BUILD BREAKER" in full_output
    assert "Infernal Crossbow" in full_output
    assert "Oil Grenade" in full_output
