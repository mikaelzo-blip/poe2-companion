"""Unit tests for gear domain schemas and deterministic item hasher."""

from datetime import datetime, timezone
import pytest

from companion.gear.hasher import compute_item_hash
from companion.gear.schema import (
    EquippedItem,
    GearAuditState,
    ItemMod,
    ItemRarity,
    ItemSlot,
    ModType,
)
from companion.state.provenance import VerificationState


def test_gear_schema_models() -> None:
    mod1 = ItemMod(
        raw_text="+45 to Maximum Life",
        mod_type=ModType.EXPLICIT,
        key="maximum_life",
        value=45,
    )
    mod2 = ItemMod(
        raw_text="+25% to Cold Resistance",
        mod_type=ModType.EXPLICIT,
        key="cold_resistance",
        value=25,
    )

    item = EquippedItem(
        slot=ItemSlot.BOOTS,
        name="Storm Tread",
        base_type="Iron Greaves",
        rarity=ItemRarity.RARE,
        level_req=45,
        required_str=50,
        explicit_mods=[mod1, mod2],
        verification=VerificationState.VERIFIED,
    )

    assert item.slot == ItemSlot.BOOTS
    assert item.name == "Storm Tread"
    assert len(item.explicit_mods) == 2
    assert item.verification == VerificationState.VERIFIED

    audit_state = GearAuditState(
        character_id="char-1",
        slots={ItemSlot.BOOTS: item},
    )
    assert audit_state.character_id == "char-1"
    assert ItemSlot.BOOTS in audit_state.slots
    assert ItemSlot.HELMET not in audit_state.slots


def test_deterministic_item_hasher() -> None:
    mod_a = ItemMod(
        raw_text="+45 to Maximum Life",
        mod_type=ModType.EXPLICIT,
        key="maximum_life",
        value=45,
    )
    mod_b = ItemMod(
        raw_text="+25% to Cold Resistance",
        mod_type=ModType.EXPLICIT,
        key="cold_resistance",
        value=25,
    )

    item1 = EquippedItem(
        slot=ItemSlot.BOOTS,
        name="Storm Tread",
        base_type="Iron Greaves",
        rarity=ItemRarity.RARE,
        level_req=45,
        explicit_mods=[mod_a, mod_b],
    )

    # item2 has reversed mod ordering but identical contents
    item2 = EquippedItem(
        slot=ItemSlot.BOOTS,
        name="Storm Tread",
        base_type="Iron Greaves",
        rarity=ItemRarity.RARE,
        level_req=45,
        explicit_mods=[mod_b, mod_a],
    )

    hash1 = compute_item_hash(item1)
    hash2 = compute_item_hash(item2)

    assert len(hash1) == 64
    assert hash1 == hash2

    # item3 has different mod value
    mod_c = ItemMod(
        raw_text="+50 to Maximum Life",
        mod_type=ModType.EXPLICIT,
        key="maximum_life",
        value=50,
    )
    item3 = EquippedItem(
        slot=ItemSlot.BOOTS,
        name="Storm Tread",
        base_type="Iron Greaves",
        rarity=ItemRarity.RARE,
        level_req=45,
        explicit_mods=[mod_c, mod_b],
    )
    hash3 = compute_item_hash(item3)
    assert hash3 != hash1
