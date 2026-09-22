"""Unit tests for screen classification, panel parsing, and multi-capture verification."""

from __future__ import annotations

import pytest

from companion.state.provenance import VerificationState
from companion.vision.classifier import classify_screen
from companion.vision.parser import evaluate_verification_state, parse_character_panel
from companion.vision.schema import CharacterPanelStats, ScreenType


PANEL_TEXT_SAMPLE = """
Character
Level 52 Blood Mage
Defences
Maximum Life: 1,450 / 1,450
Maximum Mana: 420 / 420
Spirit: 100 / 100
Armour: 1,250
Evasion Rating: 850
Resistances
Fire Resistance: 75%
Cold Resistance: 68%
Lightning Resistance: 75%
Chaos Resistance: -15%
"""

ITEM_TEXT_SAMPLE = """
Rarity: Rare
Gloom Branch
Bone Wand
Requires Level: 48, Int: 124
Item Level: 55
+22% Spell Damage
Adds 5 to 35 Lightning Damage to Spells
"""


def test_classify_screen_types() -> None:
    screen_type, conf = classify_screen(PANEL_TEXT_SAMPLE)
    assert screen_type == ScreenType.CHARACTER_PANEL
    assert conf >= 0.8

    screen_type_item, conf_item = classify_screen(ITEM_TEXT_SAMPLE)
    assert screen_type_item == ScreenType.ITEM_TOOLTIP
    assert conf_item >= 0.8

    screen_type_unk, conf_unk = classify_screen("Walking through the mud flats killing zombies.")
    assert screen_type_unk == ScreenType.UNKNOWN
    assert conf_unk <= 0.2


def test_parse_character_panel_stats() -> None:
    stats = parse_character_panel(PANEL_TEXT_SAMPLE)
    assert stats.life == 1450
    assert stats.mana == 420
    assert stats.spirit == 100
    assert stats.armour == 1250
    assert stats.evasion == 850
    assert stats.fire_res == 75
    assert stats.cold_res == 68
    assert stats.lightning_res == 75
    assert stats.chaos_res == -15


def test_evaluate_verification_state_single_source() -> None:
    stats1 = parse_character_panel(PANEL_TEXT_SAMPLE)
    final_stats, state = evaluate_verification_state([stats1])
    assert final_stats == stats1
    assert state == VerificationState.SINGLE_SOURCE


def test_evaluate_verification_state_verified_dual_capture() -> None:
    stats1 = parse_character_panel(PANEL_TEXT_SAMPLE)
    stats2 = parse_character_panel(PANEL_TEXT_SAMPLE)
    final_stats, state = evaluate_verification_state([stats1, stats2])
    assert final_stats == stats1
    assert state == VerificationState.VERIFIED


def test_evaluate_verification_state_conflicting() -> None:
    stats1 = parse_character_panel(PANEL_TEXT_SAMPLE)
    stats2 = CharacterPanelStats(
        life=900,
        mana=300,
        fire_res=50,
    )
    final_stats, state = evaluate_verification_state([stats1, stats2])
    assert state == VerificationState.CONFLICTING
