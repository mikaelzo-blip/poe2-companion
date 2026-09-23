"""Unit tests for modifier scope classification and double-count prevention."""

import pytest
from companion.equipment.schema import (
    ModifierScope,
    NormalizedModifierType,
    SlotType,
)
from companion.equipment.normalizer import normalize_modifier


def test_displayed_armour_local_percent_not_global():
    mod = normalize_modifier("45% increased Armour", slot=SlotType.BODY_ARMOUR)
    assert mod.scope == ModifierScope.LOCAL_ITEM_STAT
    assert mod.scope != ModifierScope.GLOBAL_CHARACTER_STAT


def test_displayed_evasion_local_flat_not_global():
    mod = normalize_modifier("+120 to Evasion Rating", slot=SlotType.HELMET)
    assert mod.scope == ModifierScope.LOCAL_ITEM_STAT
    assert mod.scope != ModifierScope.GLOBAL_CHARACTER_STAT


def test_local_weapon_physical_damage_not_generic_spell_damage():
    mod = normalize_modifier("40% increased Physical Damage", slot=SlotType.MAIN_HAND)
    assert mod.scope == ModifierScope.LOCAL_ITEM_STAT
    assert mod.scope != ModifierScope.GLOBAL_CHARACTER_STAT


def test_unknown_scope_isolated():
    mod = normalize_modifier("Curse Enemies with Level 10 Vulnerability on Hit")
    assert mod.scope == ModifierScope.UNKNOWN_SCOPE
    assert mod.modifier_type == NormalizedModifierType.UNKNOWN_MODIFIER


def test_conditional_scope_isolated():
    mod = normalize_modifier("15% increased Attack Speed if you've Killed Recently")
    assert mod.scope == ModifierScope.CONDITIONAL
