"""Unit tests for API loadout conflict detection and safe non-destructive reconciliation."""

import pytest
from companion.state.provenance import VerificationState
from companion.equipment.schema import SlotType
from companion.equipment.parser import parse_item_text
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.api_adapter import (
    GGGCharacterAPIAdapter,
    OAuthStatus,
)

MANUAL_BOOTS = """Item Class: Boots
Rarity: Rare
Manual Stride
Furtive Boots
--------
+30 to maximum Life
"""

API_PAYLOAD_DIFFERENT_BOOTS = {
    "character": {"id": "char_conf", "name": "ConflictChar"},
    "equipment": [
        {
            "slot": "Boots",
            "name": "Different API Boots",
            "typeLine": "Furtive Boots",
            "rarity": "Rare",
            "explicitMods": ["+50 to maximum Life"],
        }
    ],
}


def test_api_detects_conflict_with_manual_loadout():
    # Loadout has Manual Stride
    manual_loadout = EquippedLoadout.create_draft(character_id="char_conf")
    boots = parse_item_text(MANUAL_BOOTS, target_slot=SlotType.BOOTS)
    manual_loadout.set_slot(SlotType.BOOTS, boots)
    manual_loadout.finalize()

    adapter = GGGCharacterAPIAdapter(oauth_status=OAuthStatus.AUTHENTICATED)
    synced_loadout, _, warnings = adapter.sync_character(
        account_name="User#123",
        character_id="char_conf",
        current_loadout=manual_loadout,
        raw_api_payload=API_PAYLOAD_DIFFERENT_BOOTS,
    )

    assert synced_loadout is not None
    # Entry in BOOTS should be marked CONFLICTING
    entry = synced_loadout.get_slot(SlotType.BOOTS)
    assert entry.verification == VerificationState.CONFLICTING
    assert any("conflict" in w.lower() for w in warnings)


def test_api_adapter_overwrites_conflicts_when_requested():
    manual_loadout = EquippedLoadout.create_draft(character_id="char_conf")
    boots = parse_item_text(MANUAL_BOOTS, target_slot=SlotType.BOOTS)
    manual_loadout.set_slot(SlotType.BOOTS, boots)
    manual_loadout.finalize()

    adapter = GGGCharacterAPIAdapter(oauth_status=OAuthStatus.AUTHENTICATED)
    synced_loadout, _, warnings = adapter.sync_character(
        account_name="User#123",
        character_id="char_conf",
        current_loadout=manual_loadout,
        raw_api_payload=API_PAYLOAD_DIFFERENT_BOOTS,
        overwrite_conflicts=True,
    )

    assert synced_loadout is not None
    entry = synced_loadout.get_slot(SlotType.BOOTS)
    assert entry is not None
    assert entry.verification == VerificationState.VERIFIED
    assert entry.item.name == "Different API Boots"


def test_api_adapter_gracefully_handles_novel_patch_items_and_unknown_slots():
    novel_patch_payload = {
        "character": {"id": "patch_char", "name": "PatchChar"},
        "equipment": [
            # 1. Unknown novel slot (e.g. Charm / Trinket in a future patch)
            {
                "slot": "TrinketSlot",
                "name": "Strange Trinket",
                "typeLine": "Golden Trinket",
                "rarity": "Rare",
            },
            # 2. Corrupted / malformed novel item that cannot be parsed
            {
                "slot": "Helmet",
                "name": "",
                "typeLine": "",  # Empty name and typeLine
            },
            # 3. Valid Boots with rune and enchant mods
            {
                "slot": "Boots",
                "name": "Future Strider",
                "typeLine": "Iron Greaves",
                "rarity": "Rare",
                "runeMods": ["+10 to Strength (rune)"],
                "enchantMods": ["10% increased Movement Speed"],
                "explicitMods": ["+40 to maximum Life"],
            },
        ],
    }

    adapter = GGGCharacterAPIAdapter(oauth_status=OAuthStatus.AUTHENTICATED)
    synced_loadout, _, warnings = adapter.sync_character(
        account_name="User#123",
        character_id="patch_char",
        current_loadout=None,
        raw_api_payload=novel_patch_payload,
    )

    assert synced_loadout is not None
    # The valid boots must be successfully parsed and equipped
    assert SlotType.BOOTS in synced_loadout.known_slots
    boots_entry = synced_loadout.get_slot(SlotType.BOOTS)
    assert boots_entry is not None
    assert boots_entry.item.name == "Future Strider"
    assert boots_entry.verification == VerificationState.VERIFIED


def test_api_adapter_maps_dual_weapon_sets_and_rings():
    from companion.equipment.schema import WeaponSetContext

    dual_wep_payload = {
        "character": {"id": "dual_char", "name": "DualChar"},
        "equipment": [
            {
                "inventoryId": "Weapon",
                "name": "Dire Core",
                "typeLine": "Tense Crossbow",
                "rarity": "Rare",
                "explicitMods": ["Adds 5 to 12 Physical Damage"],
            },
            {
                "inventoryId": "Offhand",
                "name": "Iron Shield",
                "typeLine": "Round Shield",
                "rarity": "Rare",
                "explicitMods": ["+20 to maximum Life"],
            },
            {
                "inventoryId": "Weapon2",
                "name": "Blood Branch",
                "typeLine": "Quarterstaff",
                "rarity": "Rare",
                "explicitMods": ["Adds 5 to 15 Fire Damage"],
            },
            {
                "inventoryId": "Offhand2",
                "name": "Bone Focus",
                "typeLine": "Twig Focus",
                "rarity": "Rare",
                "explicitMods": ["+15 to Intelligence"],
            },
            {
                "inventoryId": "Ring",
                "name": "Gold Ring",
                "typeLine": "Gold Ring",
                "rarity": "Rare",
                "explicitMods": ["+20% to Fire Resistance"],
            },
            {
                "inventoryId": "Ring2",
                "name": "Ruby Ring",
                "typeLine": "Ruby Ring",
                "rarity": "Rare",
                "explicitMods": ["+30% to Fire Resistance"],
            },
        ],
    }

    adapter = GGGCharacterAPIAdapter(oauth_status=OAuthStatus.AUTHENTICATED)
    synced_loadout, baseline, warnings = adapter.sync_character(
        account_name="User#123",
        character_id="dual_char",
        current_loadout=None,
        raw_api_payload=dual_wep_payload,
    )

    assert synced_loadout is not None
    # Weapon Set 1
    w1_entry = synced_loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_1)
    assert w1_entry is not None
    assert w1_entry.item.name == "Dire Core"

    oh1_entry = synced_loadout.get_slot(SlotType.OFF_HAND, weapon_set=WeaponSetContext.WEAPON_SET_1)
    assert oh1_entry is not None
    assert oh1_entry.item.name == "Iron Shield"

    # Weapon Set 2
    w2_entry = synced_loadout.get_slot(SlotType.MAIN_HAND, weapon_set=WeaponSetContext.WEAPON_SET_2)
    assert w2_entry is not None
    assert w2_entry.item.name == "Blood Branch"

    oh2_entry = synced_loadout.get_slot(SlotType.OFF_HAND, weapon_set=WeaponSetContext.WEAPON_SET_2)
    assert oh2_entry is not None
    assert oh2_entry.item.name == "Bone Focus"

    # Dual Rings
    r1_entry = synced_loadout.get_slot(SlotType.RING_1)
    assert r1_entry is not None
    assert r1_entry.item.name == "Gold Ring"

    r2_entry = synced_loadout.get_slot(SlotType.RING_2)
    assert r2_entry is not None
    assert r2_entry.item.name == "Ruby Ring"
