"""End-to-end integration test for Milestone 10 official API and PoB2 comparator pipeline."""

import pytest
from companion.api import (
    ApiCircuitBreaker,
    CircuitState,
    OAuthStatus,
    Poe2ApiClient,
    build_authorization_url,
    build_user_agent,
    compare_character_with_pob2,
    create_mock_character,
    generate_pkce_pair,
    get_oauth_status,
)


def test_m10_official_api_and_pob2_end_to_end_pipeline() -> None:
    # 1. Verify PKCE generation and GGG compliant User-Agent
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    assert len(challenge) == 43

    ua = build_user_agent("poe2-test-client", "dev@example.com", "1.0.0")
    assert ua.startswith("OAuth poe2-test-client/1.0.0")

    auth_url = build_authorization_url(
        client_id="poe2-test-client",
        redirect_uri="https://localhost:8080/callback",
        scope="account:profile service:psapi",
        code_challenge=challenge,
        state="state_xyz",
    )
    assert "https://www.pathofexile.com/oauth/authorize" in auth_url
    assert f"code_challenge={challenge}" in auth_url

    # 2. Honest external credential check
    # Without environment credentials, it must report EXTERNALLY_BLOCKED
    assert get_oauth_status(env={}) == OAuthStatus.EXTERNALLY_BLOCKED
    assert get_oauth_status(env={"POE2_CLIENT_ID": "client-id"}) == OAuthStatus.EXTERNALLY_BLOCKED
    live_client = Poe2ApiClient(client_id=None)
    data, status = live_client.sync_character("test_char")
    assert data is None
    assert "EXTERNALLY_BLOCKED" in status

    # 3. 4xx circuit breaker resilience
    cb = ApiCircuitBreaker(failure_threshold=2, cooldown_seconds=60)
    cb.record_failure(429)
    assert cb.state == CircuitState.CLOSED
    cb.record_failure(429)
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False

    # 4. Structured sync using mock adapter fixture
    mock_char = create_mock_character(character_id="hero_fubgun", level=72, game_version="0.1.0")
    test_client = Poe2ApiClient(mock_data=mock_char)
    synced, sync_status = test_client.sync_character("hero_fubgun")
    assert synced is not None
    assert sync_status == "SYNC_SUCCESS"
    assert synced.level == 72
    assert len(synced.passives) > 0
    assert len(synced.equipment) > 0

    # 5. Deeper PoB2 comparison and patch drift detection
    # Case A: Same version (0.1.0), matching tree
    target_passives = list(synced.passives) + ["future_node_1"]
    cmp_result = compare_character_with_pob2(synced, target_passives, expected_game_version="0.1.0")
    assert cmp_result.patch_drift_detected is False
    assert len(cmp_result.missing_passives) == 1
    assert "future_node_1" in cmp_result.missing_passives
    assert cmp_result.completion_ratio > 0.8

    # Case B: Patch drift (game version 0.2.0 vs PoB2 export 0.1.0)
    patched_char = mock_char.model_copy(update={"game_version": "0.2.0"})
    drift_result = compare_character_with_pob2(patched_char, target_passives, expected_game_version="0.1.0")
    assert drift_result.patch_drift_detected is True
    assert drift_result.patch_drift_warning is not None
