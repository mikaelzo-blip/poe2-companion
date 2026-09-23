"""Unit tests for fail-closed PoE2 item envelope validation and rejection of invalid clipboard input."""

from pathlib import Path
from unittest.mock import patch
import pytest

from companion.cli import main
from companion.equipment.loadout_cli import (
    load_loadout,
    run_loadout_finalize,
    run_loadout_set_item,
)
from companion.equipment.parser import (
    InvalidItemClipboardError,
    parse_item_text,
    validate_poe2_item_envelope,
)
from companion.equipment.schema import NormalizedModifierType, SlotType

ENGLISH_PARAGRAPH = """
This build relies on high evasion and movement speed to survive in maps.
Make sure you cap all elemental resistances before moving to tier 10 maps.
Energy shield recharge rate is also helpful for hybrid characters.
"""

UAT_PROMPT_TEXT = """Continue Equipment Intelligence REAL LIVE UAT using the EXISTING persisted runtime:

runtime/equipment_uat_live

This is UAT STEP 1: CAPTURE CURRENT BOOTS.

The user has ALREADY manually hovered the currently equipped boots in
PoE2 and pressed Ctrl+C.

==================================================
1. CAPTURE CURRENT BOOTS
==================================================

Read the live clipboard through the production command corresponding to:
gear loadout set-clipboard --slot boots
"""

MARKDOWN_INSTRUCTIONS = """
# Gear Evaluation Checklist
- item name: Iron Greaves
- base type: Boots
- rarity: Rare
* Check life rolls
* Check resistance tiers
"""

URL_CLIPBOARD = "https://www.pathofexile.com/trade2/search/poe2/Standard/abc123xyz"

EMPTY_CLIPBOARD = "   \n\t  \n  "

VALID_RARE_BOOTS = """Item Class: Boots
Rarity: Rare
Loath Trail
Furtive Boots
--------
Requirements:
Level: 45
Dex: 42
--------
+66 to maximum Life
+28% to Lightning Resistance
+10% increased Movement Speed
"""

VALID_ITEM_WITH_UNKNOWN_MOD = """Item Class: Boots
Rarity: Rare
Loath Trail
Furtive Boots
--------
Requirements:
Level: 45
--------
+66 to maximum Life
30% chance to avoid being frozen by glacial cascades
"""


def test_reject_ordinary_english_paragraph():
    """A. Ordinary English paragraph is rejected."""
    with pytest.raises(InvalidItemClipboardError) as exc_info:
        parse_item_text(ENGLISH_PARAGRAPH)
    assert "Clipboard does not contain recognizable PoE2 item text" in str(exc_info.value)


def test_reject_uat_prompt_text():
    """B. The exact style of UAT prompt text that caused the defect is rejected."""
    with pytest.raises(InvalidItemClipboardError) as exc_info:
        parse_item_text(UAT_PROMPT_TEXT)
    assert "Clipboard does not contain recognizable PoE2 item text" in str(exc_info.value)


def test_reject_markdown_instructions():
    """C. Markdown/bulleted instructions are rejected."""
    with pytest.raises(InvalidItemClipboardError) as exc_info:
        parse_item_text(MARKDOWN_INSTRUCTIONS)
    assert "Clipboard does not contain recognizable PoE2 item text" in str(exc_info.value)


def test_reject_url_plain_text():
    """D. URL/plain text clipboard is rejected."""
    with pytest.raises(InvalidItemClipboardError) as exc_info:
        parse_item_text(URL_CLIPBOARD)
    assert "Clipboard does not contain recognizable PoE2 item text" in str(exc_info.value)


def test_reject_empty_clipboard():
    """E. Empty clipboard is rejected."""
    with pytest.raises(InvalidItemClipboardError) as exc_info:
        parse_item_text(EMPTY_CLIPBOARD)
    assert "Clipboard does not contain recognizable PoE2 item text" in str(exc_info.value)


def test_accept_valid_rare_boots():
    """F. Valid Rare boots with known modifiers are accepted."""
    item = parse_item_text(VALID_RARE_BOOTS)
    assert item.name == "Loath Trail"
    assert item.base_type == "Furtive Boots"
    assert item.rarity == "rare"
    assert item.slot == SlotType.BOOTS
    mod_types = [m.modifier_type for m in item.modifiers]
    assert NormalizedModifierType.MAXIMUM_LIFE in mod_types
    assert NormalizedModifierType.LIGHTNING_RESISTANCE in mod_types
    assert NormalizedModifierType.MOVEMENT_SPEED in mod_types


def test_accept_valid_item_with_unknown_modifier():
    """G. Valid item containing one unknown modifier is accepted and preserved."""
    item = parse_item_text(VALID_ITEM_WITH_UNKNOWN_MOD)
    assert item.name == "Loath Trail"
    assert item.base_type == "Furtive Boots"
    assert item.rarity == "rare"

    mod_types = [m.modifier_type for m in item.modifiers]
    assert NormalizedModifierType.MAXIMUM_LIFE in mod_types
    assert NormalizedModifierType.UNKNOWN_MODIFIER in mod_types

    unknown_mods = [m for m in item.modifiers if m.modifier_type == NormalizedModifierType.UNKNOWN_MODIFIER]
    assert len(unknown_mods) == 1
    assert "30% chance to avoid being frozen" in unknown_mods[0].raw_text


def test_invalid_set_clipboard_no_draft_mutation(tmp_path: Path, capsys):
    """H. Invalid set-clipboard fails safely and does not mutate draft slot."""
    runtime_dir = tmp_path / "runtime"
    char_id = "test_char_h"

    invalid_file = tmp_path / "invalid.txt"
    invalid_file.write_text(UAT_PROMPT_TEXT, encoding="utf-8")

    code = main([
        "gear", "loadout", "set-clipboard",
        "--slot", "boots",
        "--file", str(invalid_file),
        "--runtime", str(runtime_dir),
        "--character-id", char_id,
    ])
    assert code == 1

    captured = capsys.readouterr()
    assert "Error setting loadout slot:" in captured.err
    assert "Clipboard does not contain recognizable PoE2 item text" in captured.err

    loadout = load_loadout(runtime_dir, char_id)
    assert loadout.get_slot(SlotType.BOOTS) is None


def test_invalid_promote_candidate_no_loadout_mutation(tmp_path: Path, capsys):
    """I. Invalid promote-candidate does not mutate loadout or change revision."""
    runtime_dir = tmp_path / "runtime"
    char_id = "test_char_i"

    # Set up valid initial loadout with revision 1
    run_loadout_set_item(runtime_dir, char_id, "boots", VALID_RARE_BOOTS)
    run_loadout_finalize(runtime_dir, char_id)

    loadout_before = load_loadout(runtime_dir, char_id)
    assert loadout_before.revision == 1
    assert loadout_before.get_slot(SlotType.BOOTS).item.name == "Loath Trail"

    invalid_file = tmp_path / "invalid_candidate.txt"
    invalid_file.write_text(ENGLISH_PARAGRAPH, encoding="utf-8")

    code = main([
        "gear", "loadout", "promote-candidate",
        "--slot", "boots",
        "--file", str(invalid_file),
        "--runtime", str(runtime_dir),
        "--character-id", char_id,
    ])
    assert code == 1

    captured = capsys.readouterr()
    assert "Error promoting candidate:" in captured.err
    assert "Clipboard does not contain recognizable PoE2 item text" in captured.err

    loadout_after = load_loadout(runtime_dir, char_id)
    assert loadout_after.revision == 1
    assert loadout_after.get_slot(SlotType.BOOTS).item.name == "Loath Trail"


def test_invalid_evaluate_file_safe_failure(tmp_path: Path, capsys):
    """J. Invalid evaluate file fails safely with user-facing message and non-zero exit."""
    runtime_dir = tmp_path / "runtime"
    char_id = "test_char_j"

    invalid_file = tmp_path / "invalid_eval.txt"
    invalid_file.write_text(URL_CLIPBOARD, encoding="utf-8")

    code = main([
        "gear", "evaluate",
        "--file", str(invalid_file),
        "--runtime", str(runtime_dir),
        "--character-id", char_id,
    ])
    assert code == 1

    captured = capsys.readouterr()
    assert "Error evaluating candidate file:" in captured.err
    assert "Clipboard does not contain recognizable PoE2 item text" in captured.err


def test_invalid_inspect_clipboard_safe_failure(tmp_path: Path, capsys):
    """Invalid inspect-clipboard fails safely with user-facing error and non-zero exit."""
    runtime_dir = tmp_path / "runtime"
    char_id = "test_char_clip"

    with patch("companion.equipment.clipboard.get_clipboard_text", return_value=UAT_PROMPT_TEXT):
        code = main([
            "gear", "inspect-clipboard",
            "--slot", "boots",
            "--runtime", str(runtime_dir),
            "--character-id", char_id,
        ])
    assert code == 1

    captured = capsys.readouterr()
    assert "Error inspecting clipboard:" in captured.err
    assert "Clipboard does not contain recognizable PoE2 item text" in captured.err
