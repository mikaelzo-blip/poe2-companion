"""Unit tests for PoE2 dual-resistance modifiers and ItemContribution aggregation."""

import pytest
from companion.equipment.contribution import build_item_contribution
from companion.equipment.normalizer import normalize_modifier
from companion.equipment.parser import parse_item_text
from companion.equipment.schema import ModifierScope, NormalizedModifierType, SlotType


def test_normalize_dual_resistances():
    mod_cold_chaos = normalize_modifier("+13% to Cold and Chaos Resistances")
    assert mod_cold_chaos is not None
    assert mod_cold_chaos.modifier_type == NormalizedModifierType.COLD_CHAOS_RESISTANCE
    assert mod_cold_chaos.value == 13.0

    mod_light_fire = normalize_modifier("+15% to Lightning and Fire Resistances")
    assert mod_light_fire is not None
    assert mod_light_fire.modifier_type == NormalizedModifierType.FIRE_LIGHTNING_RESISTANCE
    assert mod_light_fire.value == 15.0

    mod_fire = normalize_modifier("+20% to Fire Resistance")
    assert mod_fire is not None
    assert mod_fire.modifier_type == NormalizedModifierType.FIRE_RESISTANCE
    assert mod_fire.value == 20.0

    mod_all = normalize_modifier("+10% to all Elemental Resistances")
    assert mod_all is not None
    assert mod_all.modifier_type == NormalizedModifierType.ALL_ELEMENTAL_RESISTANCE
    assert mod_all.value == 10.0


def test_normalize_all_dual_resistance_pairs_and_orders():
    test_cases = [
        ("+10% to Fire and Cold Resistances", NormalizedModifierType.FIRE_COLD_RESISTANCE),
        ("+10% to Cold and Fire Resistances", NormalizedModifierType.FIRE_COLD_RESISTANCE),
        ("+12% to Fire and Lightning Resistances", NormalizedModifierType.FIRE_LIGHTNING_RESISTANCE),
        ("+12% to Lightning and Fire Resistances", NormalizedModifierType.FIRE_LIGHTNING_RESISTANCE),
        ("+14% to Fire and Chaos Resistances", NormalizedModifierType.FIRE_CHAOS_RESISTANCE),
        ("+14% to Chaos and Fire Resistances", NormalizedModifierType.FIRE_CHAOS_RESISTANCE),
        ("+16% to Cold and Lightning Resistances", NormalizedModifierType.COLD_LIGHTNING_RESISTANCE),
        ("+16% to Lightning and Cold Resistances", NormalizedModifierType.COLD_LIGHTNING_RESISTANCE),
        ("+18% to Cold and Chaos Resistances", NormalizedModifierType.COLD_CHAOS_RESISTANCE),
        ("+18% to Chaos and Cold Resistances", NormalizedModifierType.COLD_CHAOS_RESISTANCE),
        ("+20% to Lightning and Chaos Resistances", NormalizedModifierType.LIGHTNING_CHAOS_RESISTANCE),
        ("+20% to Chaos and Lightning Resistances", NormalizedModifierType.LIGHTNING_CHAOS_RESISTANCE),
    ]
    for text, expected_type in test_cases:
        mod = normalize_modifier(text)
        assert mod is not None, f"Failed to normalize {text}"
        assert mod.modifier_type == expected_type


def test_dual_resistance_identical_elements_fall_through():
    # If both elements are the same, RE_DUAL_RES falls through
    mod = normalize_modifier("+15% to Fire and Fire Resistances")
    assert mod is not None
    assert mod.modifier_type == NormalizedModifierType.UNKNOWN_MODIFIER


def test_dual_resistance_conditional_scope():
    mod = normalize_modifier("+13% to Cold and Chaos Resistances while on Low Life")
    assert mod is not None
    assert mod.modifier_type == NormalizedModifierType.COLD_CHAOS_RESISTANCE
    assert mod.scope == ModifierScope.CONDITIONAL
    assert mod.value == 13.0


def test_dual_resistance_clipboard_ring_contribution():
    ring_text = """Item Class: Rings
Rarity: Rare
Loath Band
Iron Ring
--------
Requirements:
Level: 40
--------
+13% to Cold and Chaos Resistances
+10% to Fire Resistance
"""
    item = parse_item_text(ring_text, target_slot=SlotType.RING_1)
    contrib = build_item_contribution(item)

    assert contrib.cold_res_delta == 13.0
    assert contrib.chaos_res_delta == 13.0
    assert contrib.fire_res_delta == 10.0
    assert contrib.lightning_res_delta == 0.0
