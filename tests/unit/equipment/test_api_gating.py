"""Unit tests for OAuth 2.1 status gating and MANUAL_ONLY operational mode."""

import pytest
from companion.equipment.api_adapter import (
    GGGCharacterAPIAdapter,
    OAuthStatus,
    OperationalMode,
)


def test_disconnected_oauth_forces_manual_only_mode():
    adapter = GGGCharacterAPIAdapter(oauth_status=OAuthStatus.DISCONNECTED)
    assert adapter.operational_mode == OperationalMode.MANUAL_ONLY
    assert adapter.is_api_available() is False

    loadout, baseline, warnings = adapter.sync_character(
        account_name="User#123",
        character_id="char_1",
    )
    assert loadout is None
    assert baseline is None
    assert any("MANUAL_ONLY" in w or "authentication required" in w.lower() for w in warnings)


def test_expired_token_blocks_api_and_remains_manual():
    adapter = GGGCharacterAPIAdapter(oauth_status=OAuthStatus.EXPIRED)
    assert adapter.is_api_available() is False
    loadout, baseline, warnings = adapter.sync_character(
        account_name="User#123",
        character_id="char_1",
    )
    assert loadout is None
    assert any("expired" in w.lower() or "authentication" in w.lower() for w in warnings)
