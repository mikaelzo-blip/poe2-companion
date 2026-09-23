"""Unit tests for modifier normalizer distinguishing scopes and types."""

import pytest
from companion.equipment.schema import (
    ModifierScope,
    NormalizedModifierType,
    SlotType,
)
from companion.equipment.normalizer import normalize_modifier, normalize_modifier_text


def test_normalize_life():
    mod = normalize_modifier("+66 to maximum Life")
    assert mod.modifier_type == NormalizedModifierType.MAXIMUM_LIFE
    assert mod.scope == ModifierScope.GLOBAL_CHARACTER_STAT
    assert mod.value == 66.0


def test_normalize_resistances():
    fire_mod = normalize_modifier("+35% to Fire Resistance")
    assert fire_mod.modifier_type == NormalizedModifierType.FIRE_RESISTANCE
    assert fire_mod.scope == ModifierScope.GLOBAL_CHARACTER_STAT
    assert fire_mod.value == 35.0

    cold_mod = normalize_modifier("+28% to Cold Resistance")
    assert cold_mod.modifier_type == NormalizedModifierType.COLD_RESISTANCE
    assert cold_mod.value == 28.0

    light_mod = normalize_modifier("+40% to Lightning Resistance")
    assert light_mod.modifier_type == NormalizedModifierType.LIGHTNING_RESISTANCE
    assert light_mod.value == 40.0

    chaos_mod = normalize_modifier("+15% to Chaos Resistance")
    assert chaos_mod.modifier_type == NormalizedModifierType.CHAOS_RESISTANCE
    assert chaos_mod.value == 15.0


def test_normalize_attributes():
    str_mod = normalize_modifier("+14 to Strength")
    assert str_mod.modifier_type == NormalizedModifierType.STRENGTH
    assert str_mod.scope == ModifierScope.GLOBAL_CHARACTER_STAT
    assert str_mod.value == 14.0

    dex_mod = normalize_modifier("+25 to Dexterity")
    assert dex_mod.modifier_type == NormalizedModifierType.DEXTERITY
    assert dex_mod.value == 25.0

    int_mod = normalize_modifier("+20 to Intelligence")
    assert int_mod.modifier_type == NormalizedModifierType.INTELLIGENCE
    assert int_mod.value == 20.0


def test_normalize_movement_speed():
    ms_mod = normalize_modifier("+10% increased Movement Speed")
    assert ms_mod.modifier_type == NormalizedModifierType.MOVEMENT_SPEED
    assert ms_mod.scope == ModifierScope.GLOBAL_CHARACTER_STAT
    assert ms_mod.value == 10.0


def test_normalize_local_defense_modifiers():
    armour_inc = normalize_modifier("+42% increased Armour", slot=SlotType.BODY_ARMOUR)
    assert armour_inc.modifier_type == NormalizedModifierType.LOCAL_ARMOUR
    assert armour_inc.scope == ModifierScope.LOCAL_ITEM_STAT
    assert armour_inc.value == 42.0

    eva_flat = normalize_modifier("+55 to Evasion Rating", slot=SlotType.BOOTS)
    assert eva_flat.modifier_type == NormalizedModifierType.LOCAL_EVASION
    assert eva_flat.scope == ModifierScope.LOCAL_ITEM_STAT
    assert eva_flat.value == 55.0


def test_normalize_fire_damage_variants():
    attack_fire = normalize_modifier("Adds 12 to 24 Fire Damage to Attacks")
    assert attack_fire.modifier_type == NormalizedModifierType.FLAT_FIRE_DAMAGE_ATTACK
    assert attack_fire.scope == ModifierScope.BUILD_MECHANIC
    assert attack_fire.value == 18.0

    spell_fire = normalize_modifier("Adds 10 to 20 Fire Damage to Spells")
    assert spell_fire.modifier_type == NormalizedModifierType.FLAT_FIRE_DAMAGE_SPELL
    assert spell_fire.scope == ModifierScope.BUILD_MECHANIC

    extra_fire = normalize_modifier("Gain 8% of Physical Damage as Extra Fire Damage")
    assert extra_fire.modifier_type == NormalizedModifierType.EXTRA_FIRE_DAMAGE
    assert extra_fire.scope == ModifierScope.BUILD_MECHANIC
    assert extra_fire.value == 8.0

    inc_fire = normalize_modifier("22% increased Fire Damage")
    assert inc_fire.modifier_type == NormalizedModifierType.INCREASED_FIRE_DAMAGE
    assert inc_fire.scope == ModifierScope.GLOBAL_CHARACTER_STAT
    assert inc_fire.value == 22.0

    gem_level = normalize_modifier("+1 to Level of all Fire Spell Skill Gems")
    assert gem_level.modifier_type == NormalizedModifierType.FIRE_SPELL_LEVEL
    assert gem_level.scope == ModifierScope.BUILD_MECHANIC
    assert gem_level.value == 1.0


def test_normalize_unknown_and_conditional_modifiers():
    unknown_mod = normalize_modifier("10% increased Light Radius")
    assert unknown_mod.modifier_type == NormalizedModifierType.UNKNOWN_MODIFIER
    assert unknown_mod.scope == ModifierScope.UNKNOWN_SCOPE

    cond_mod = normalize_modifier("Gain 8% of Physical Damage as Extra Fire Damage during Focus")
    assert cond_mod.scope == ModifierScope.CONDITIONAL
