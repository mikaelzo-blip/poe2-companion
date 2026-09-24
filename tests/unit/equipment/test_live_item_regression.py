"""Regression tests using live PoE2 clipboard item text for The Knight-errant Mail Sabatons."""

import pytest
from companion.equipment.parser import parse_item_text, validate_poe2_item_envelope
from companion.equipment.contribution import build_item_contribution
from companion.equipment.schema import (
    ModifierScope,
    NormalizedModifierType,
    SlotOccupancy,
    SlotType,
)
from companion.state.provenance import VerificationState

KNIGHT_ERRANT_BOOTS_RAW = """Item Class: Boots
Rarity: Unique
The Knight-errant
Mail Sabatons
--------
Armour: 32 (augmented)
Evasion Rating: 25 (augmented)
--------
Requires: Level 6
--------
Item Level: 15
--------
{ Unique Modifier — Armour, Evasion }
45(30-50)% increased Armour and Evasion
{ Unique Modifier }
+30(30-50) to Stun Threshold
{ Unique Modifier — Speed }
10% increased Movement Speed
{ Unique Modifier — Armour, Evasion }
Iron Reflexes — Unscalable Value
{ Unique Modifier }
+45(30-50) to Ailment Threshold
--------
Some search forever for their path.
"""


def test_knight_errant_boots_regression_fixture():
    # 1. Valid PoE2 item accepted by envelope validation
    validate_poe2_item_envelope(KNIGHT_ERRANT_BOOTS_RAW)

    # 2. Parse item
    item = parse_item_text(KNIGHT_ERRANT_BOOTS_RAW)

    # Identity & Rarity
    assert item.name == "The Knight-errant"
    assert item.base_type == "Mail Sabatons"
    assert item.rarity == "unique"

    # Slot & Occupancy
    assert item.slot == SlotType.BOOTS
    assert item.slot_occupancy == SlotOccupancy.SINGLE_SLOT
    assert item.slot_conflict_topology.occupied_slots == [SlotType.BOOTS]
    assert item.slot_conflict_topology.conflicting_slots == [SlotType.BOOTS]
    assert item.slot_conflict_topology.is_known is True

    # Requirements & Properties
    assert item.required_level == 6
    assert item.required_str == 0
    assert item.required_dex == 0
    assert item.required_int == 0
    assert item.item_level == 15

    # Displayed Defenses
    assert item.local_armour == 32
    assert item.local_evasion == 25
    assert item.local_energy_shield == 0

    # Annotations filtered from modifiers and stored as evidence
    assert len(item.annotations) == 5
    assert "{ Unique Modifier — Armour, Evasion }" in item.annotations
    assert "{ Unique Modifier }" in item.annotations
    assert "{ Unique Modifier — Speed }" in item.annotations
    assert not any("{" in m.raw_text for m in item.modifiers)
    assert not any("modifier" in m.raw_text.lower() for m in item.modifiers)

    # Flavor text separated and not in modifiers
    assert item.flavor_text == "Some search forever for their path."
    assert not any(m.raw_text == "Some search forever for their path." for m in item.modifiers)

    # Exactly 5 real modifiers
    assert len(item.modifiers) == 5

    # 1) Local increased Armour/Evasion
    local_defense_mod = next(
        m for m in item.modifiers if m.modifier_type == NormalizedModifierType.LOCAL_ARMOUR_AND_EVASION
    )
    assert local_defense_mod.scope == ModifierScope.LOCAL_ITEM_STAT
    assert local_defense_mod.value == 45.0
    assert local_defense_mod.raw_text == "45(30-50)% increased Armour and Evasion"

    # 2) Movement Speed
    ms_mod = next(m for m in item.modifiers if m.modifier_type == NormalizedModifierType.MOVEMENT_SPEED)
    assert ms_mod.scope == ModifierScope.GLOBAL_CHARACTER_STAT
    assert ms_mod.value == 10.0

    # 3) Iron Reflexes special mechanic text
    iron_reflexes_mod = next(
        m for m in item.modifiers if m.modifier_type == NormalizedModifierType.SPECIAL_MECHANIC
    )
    assert iron_reflexes_mod.scope == ModifierScope.BUILD_MECHANIC
    assert iron_reflexes_mod.verification_state == VerificationState.UNKNOWN
    assert iron_reflexes_mod.raw_text == "Iron Reflexes — Unscalable Value"

    # 4 & 5) Unsupported Stun/Ailment Threshold remain unknown
    unknown_mods = [m for m in item.modifiers if m.modifier_type == NormalizedModifierType.UNKNOWN_MODIFIER]
    assert len(unknown_mods) == 2
    unknown_texts = {m.raw_text for m in unknown_mods}
    assert "+30(30-50) to Stun Threshold" in unknown_texts
    assert "+45(30-50) to Ailment Threshold" in unknown_texts
    for umod in unknown_mods:
        assert umod.scope == ModifierScope.UNKNOWN_SCOPE
        assert umod.verification_state == VerificationState.UNKNOWN

    # ItemContribution aggregation and no-double-count invariant
    contrib = build_item_contribution(item)
    assert contrib.slot == SlotType.BOOTS
    assert contrib.local_armour == 32
    assert contrib.local_evasion == 25
    assert contrib.local_energy_shield == 0
    assert contrib.movement_speed_delta == 10.0
    assert contrib.life_delta == 0.0
    assert contrib.fire_res_delta == 0.0
    # No double counting: local % increased Armour/Evasion is NOT in global or unknown modifiers
    assert not any(m.modifier_type == NormalizedModifierType.LOCAL_ARMOUR_AND_EVASION for m in contrib.global_modifiers)
    assert not any(m.modifier_type == NormalizedModifierType.LOCAL_ARMOUR_AND_EVASION for m in contrib.unknown_modifiers)
    # Iron Reflexes is in build_mechanic_modifiers with UNKNOWN verification
    assert len(contrib.build_mechanic_modifiers) == 1
    assert contrib.build_mechanic_modifiers[0].raw_text == "Iron Reflexes — Unscalable Value"
    assert contrib.build_mechanic_modifiers[0].verification_state == VerificationState.UNKNOWN
    # Unknown modifiers only contain Stun and Ailment threshold
    assert len(contrib.unknown_modifiers) == 2
