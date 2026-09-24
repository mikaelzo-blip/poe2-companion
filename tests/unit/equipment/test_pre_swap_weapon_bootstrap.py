"""TDD tests for pre-swap weapon bootstrap and candidate comparison."""

from pathlib import Path
import pytest

from companion.equipment.loadout_cli import load_loadout, run_loadout_set_item
from companion.equipment.live_watcher import run_live_watcher
from companion.equipment.rules import BuildProgressionStage
from companion.equipment.schema import SlotType, WeaponSetContext
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore

FIRST_CROSSBOW = """Item Class: Crossbows
Rarity: Rare
Iron Crossbow
Varnished Crossbow
--------
Physical Damage: 25-50
Critical Strike Chance: 5.00%
Attacks per Second: 1.20
--------
Requirements:
Level: 16
--------
+20 to maximum Life
+10% to Fire Resistance
"""

SECOND_CROSSBOW = """Item Class: Crossbows
Rarity: Rare
Doom Bolt
Varnished Crossbow
--------
Physical Damage: 35-70
Critical Strike Chance: 5.00%
Attacks per Second: 1.20
--------
Requirements:
Level: 18
--------
+35 to maximum Life
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


@pytest.mark.parametrize(
    "stage",
    [
        BuildProgressionStage.LEVELING_1_14,
        BuildProgressionStage.LEVELING_15_32,
        BuildProgressionStage.LEVELING_33_51,
    ],
)
def test_pre_swap_crossbow_bootstrap_only_learns_weapon_1(tmp_path: Path, stage: BuildProgressionStage):
    """During pre-swap (lvl 1-14, 15-32, 33-51), first crossbow learns Weapon 1, second is candidate."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_id = "test_preswap_char"

    store = CharacterStateStore(runtime_dir)
    store.save_character(
        CharacterState(
            character_id=char_id,
            character_name="Hunter",
            build_progression={"active_stage": stage.value},
        )
    )
    store.set_active_character(char_id)

    clipboard_items = [FIRST_CROSSBOW, SECOND_CROSSBOW]

    def mock_reader():
        if clipboard_items:
            return clipboard_items.pop(0)
        raise KeyboardInterrupt()

    output_lines: list[str] = []
    run_live_watcher(
        runtime_dir=runtime_dir,
        character_id=char_id,
        stage=stage,
        bootstrap=True,
        weapon_set=None,
        clipboard_reader=mock_reader,
        output_writer=output_lines.append,
        poll_interval=0.001,
    )

    full_output = "\n".join(output_lines)

    # 1. First crossbow is learned as Weapon 1 / Weapon Set 1
    assert "CURRENT WEAPON 1 LEARNED" in full_output or "CURRENT WEAPON SET 1 LEARNED" in full_output
    assert "Iron Crossbow" in full_output

    # 2. Second crossbow must NOT be learned as Weapon Set 2
    assert "CURRENT WEAPON SET 2 LEARNED" not in full_output
    assert "CURRENT WEAPON 2 LEARNED" not in full_output

    # 3. Second crossbow is evaluated as a CANDIDATE against Weapon 1 (Iron Crossbow)
    assert "vs Iron Crossbow" in full_output

    # 4. Check loadout state
    loadout = load_loadout(runtime_dir, char_id)
    w1 = loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_1)
    w2 = loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_2)
    assert w1 is not None and w1.item is not None
    assert w1.item.name == "Iron Crossbow"
    assert w2 is None, "Weapon Set 2 must NOT be learned during pre-swap crossbow bootstrap"


def test_pre_swap_normal_mode_crossbow_evaluates_against_weapon_1_without_flag(tmp_path: Path):
    """In normal mode (bootstrap=False) during pre-swap, a crossbow defaults to Weapon Set 1 without ambiguity error."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_id = "test_normal_preswap"

    store = CharacterStateStore(runtime_dir)
    store.save_character(
        CharacterState(
            character_id=char_id,
            character_name="Hunter",
            build_progression={"active_stage": "lvl 15-32"},
        )
    )
    store.set_active_character(char_id)

    # Pre-populate Weapon Set 1 with Iron Crossbow
    run_loadout_set_item(
        runtime_dir,
        char_id,
        SlotType.MAIN_HAND.value,
        FIRST_CROSSBOW,
        weapon_set_name="set_1",
    )

    clipboard_items = [SECOND_CROSSBOW]

    def mock_reader():
        if clipboard_items:
            return clipboard_items.pop(0)
        raise KeyboardInterrupt()

    output_lines: list[str] = []
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
    # Must NOT report ambiguity
    assert "WEAPON SET CONTEXT AMBIGUOUS" not in full_output
    # Must compare against Iron Crossbow
    assert "Doom Bolt" in full_output
    assert "vs Iron Crossbow" in full_output


def test_post_swap_dual_set_bootstrap_model(tmp_path: Path):
    """At lvl 52 Swap and later, preserve real dual-set model: Set 1 = Staff, Set 2 = Crossbow."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    char_id = "test_postswap_char"

    store = CharacterStateStore(runtime_dir)
    store.save_character(
        CharacterState(
            character_id=char_id,
            character_name="SwappedHero",
            build_progression={"active_stage": "lvl 52 Swap"},
        )
    )
    store.set_active_character(char_id)

    # In post-swap, user copies Staff then Crossbow in bootstrap mode
    clipboard_items = [STAFF_TEXT, SECOND_CROSSBOW]

    def mock_reader():
        if clipboard_items:
            return clipboard_items.pop(0)
        raise KeyboardInterrupt()

    output_lines: list[str] = []
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
    assert "✓ CURRENT WEAPON SET 1 LEARNED" in full_output
    assert "Gloom Branch" in full_output
    assert "✓ CURRENT WEAPON SET 2 LEARNED" in full_output
    assert "Doom Bolt" in full_output

    loadout = load_loadout(runtime_dir, char_id)
    w1 = loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_1)
    w2 = loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_2)
    assert w1 is not None and w1.item.name == "Gloom Branch"
    assert w2 is not None and w2.item.name == "Doom Bolt"

