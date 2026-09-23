"""Unit tests for GGG API adapter capabilities, payload mapping, and private profile handling."""

import pytest
from companion.state.provenance import VerificationState
from companion.equipment.baseline import BaselineSource
from companion.equipment.api_adapter import (
    GGGCharacterAPIAdapter,
    OAuthStatus,
    OperationalMode,
)

SAMPLE_GGG_PAYLOAD = {
    "character": {
        "id": "char_api_1",
        "name": "FubgunBlast",
        "level": 92,
        "class": "Sorceress",
    },
    "equipment": [
        {
            "slot": "Boots",
            "name": "Loath Trail",
            "typeLine": "Furtive Boots",
            "rarity": "Rare",
            "ilvl": 84,
            "explicitMods": [
                "+66 to maximum Life",
                "+28% to Lightning Resistance",
                "+10% increased Movement Speed",
            ],
        }
    ],
}


def test_api_adapter_maps_official_payload():
    adapter = GGGCharacterAPIAdapter(oauth_status=OAuthStatus.AUTHENTICATED)
    loadout, baseline, warnings = adapter.sync_character(
        account_name="Fubgun#1234",
        character_id="char_api_1",
        raw_api_payload=SAMPLE_GGG_PAYLOAD,
    )

    assert loadout is not None
    assert loadout.is_finalized is True
    assert loadout.revision == 1
    boots = loadout.get_slot(loadout.known_slots[0])
    assert boots is not None
    assert boots.item.name == "Loath Trail"
    assert boots.source == BaselineSource.GGG_OFFICIAL_API


def test_api_adapter_handles_hidden_profile():
    adapter = GGGCharacterAPIAdapter(oauth_status=OAuthStatus.AUTHENTICATED)
    loadout, baseline, warnings = adapter.sync_character(
        account_name="PrivateUser#0000",
        character_id="char_priv",
        raw_api_payload={"error": "Profile is private"},
    )

    assert loadout is None
    assert baseline is None
    assert any("private" in w.lower() or "hidden" in w.lower() for w in warnings)
