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
