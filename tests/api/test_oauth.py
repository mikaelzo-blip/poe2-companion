"""Unit tests for Milestone 10 OAuth PKCE, User-Agent enforcement, and status checks."""

import base64
import hashlib
import pytest
from companion.api.oauth import (
    OAuthStatus,
    build_authorization_url,
    build_user_agent,
    exchange_authorization_code,
    generate_oauth_state,
    generate_pkce_pair,
    get_oauth_status,
    validate_oauth_state,
)


def test_generate_pkce_pair() -> None:
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    assert len(challenge) == 43  # base64url of 32-byte sha256 without padding

    # Verify cryptographic relation: challenge == base64url(sha256(verifier))
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    assert challenge == expected_challenge


def test_build_user_agent_format() -> None:
    ua = build_user_agent("poe2-companion", "admin@example.com", "1.0.0")
    assert ua == "OAuth poe2-companion/1.0.0 (contact: admin@example.com)"


def test_build_user_agent_validation() -> None:
    with pytest.raises(ValueError):
        build_user_agent("", "admin@example.com")
    with pytest.raises(ValueError):
        build_user_agent("client", "")


def test_get_oauth_status_externally_blocked() -> None:
    status = get_oauth_status(env={})
    assert status == OAuthStatus.EXTERNALLY_BLOCKED


def test_get_oauth_status_requires_access_token() -> None:
    assert get_oauth_status(env={"POE2_CLIENT_ID": "my_client_id"}) == OAuthStatus.EXTERNALLY_BLOCKED
    assert get_oauth_status(env={"POE2_CLIENT_ID": " my_client_id ", "POE2_ACCESS_TOKEN": "token"}) == OAuthStatus.EXTERNALLY_BLOCKED
    status = get_oauth_status(env={"POE2_CLIENT_ID": "my_client_id", "POE2_ACCESS_TOKEN": "token"})
    assert status == OAuthStatus.CONFIGURED


def test_get_oauth_status_rejects_malformed_access_token() -> None:
    status = get_oauth_status(env={"POE2_CLIENT_ID": "my_client_id", "POE2_ACCESS_TOKEN": " token "})
    assert status == OAuthStatus.EXTERNALLY_BLOCKED


def test_build_user_agent_rejects_control_characters() -> None:
    with pytest.raises(ValueError):
        build_user_agent("client" + chr(10), "admin@example.com")
    with pytest.raises(ValueError):
        build_user_agent("client", "admin@example.com" + chr(13))


def test_oauth_state_generation_and_validation() -> None:
    state = generate_oauth_state()
    assert len(state) >= 32
    assert validate_oauth_state(state, state) is True
    assert validate_oauth_state(state, state + "x") is False


def test_authorization_code_exchange_uses_pkce_and_returns_token() -> None:
    seen: dict[str, object] = {}

    def transport(url: str, body: bytes, headers: dict[str, str], timeout: float) -> dict[str, object]:
        seen.update(url=url, body=body, headers=headers, timeout=timeout)
        return {"access_token": "access-token", "token_type": "Bearer", "expires_in": 3600}

    token = exchange_authorization_code(
        token_url="https://www.pathofexile.com/oauth/token",
        client_id="client-id",
        code="auth-code",
        redirect_uri="https://localhost/callback",
        code_verifier="verifier",
        contact_email="dev@example.com",
        transport=transport,
    )

    assert token.access_token == "access-token"
    assert token.expires_in == 3600
    assert b"code_verifier=verifier" in seen["body"]
    assert seen["headers"] == {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "User-Agent": "OAuth client-id/1.0.0 (contact: dev@example.com)",
    }


def test_authorization_code_exchange_rejects_non_local_redirect() -> None:
    with pytest.raises(ValueError):
        exchange_authorization_code(
            token_url="https://www.pathofexile.com/oauth/token",
            client_id="client-id",
            code="auth-code",
            redirect_uri="https://evil.example/callback",
            code_verifier="verifier",
            transport=lambda *_args: {"access_token": "token"},
        )
def test_authorization_code_exchange_rejects_malformed_token_payload() -> None:
    with pytest.raises(ValueError):
        exchange_authorization_code(
            token_url="https://www.pathofexile.com/oauth/token",
            client_id="client-id",
            code="auth-code",
            redirect_uri="https://localhost/callback",
            code_verifier="verifier",
            transport=lambda *_args: {"access_token": ["not-a-token"]},
        )


def test_build_authorization_url() -> None:
    url = build_authorization_url(
        client_id="my_client",
        redirect_uri="https://localhost:8080/callback",
        scope="account:profile service:psapi",
        code_challenge="dummy_challenge",
        state="xyz123",
    )
    assert "https://www.pathofexile.com/oauth/authorize" in url
    assert "client_id=my_client" in url
    assert "code_challenge=dummy_challenge" in url
    assert "code_challenge_method=S256" in url
    assert "response_type=code" in url
