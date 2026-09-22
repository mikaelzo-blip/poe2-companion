"""OAuth 2.0 PKCE implementation and User-Agent compliance for PoE2 official API."""

from __future__ import annotations

import base64
from enum import Enum
import hashlib
import hmac
import json
import os
import secrets
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping


class OAuthStatus(str, Enum):
    """External status of official API OAuth credentials."""
    CONFIGURED = "CONFIGURED"
    EXTERNALLY_BLOCKED = "EXTERNALLY_BLOCKED"


def generate_pkce_pair() -> tuple[str, str]:
    """Generate high-entropy RFC 7636 PKCE code_verifier and code_challenge."""
    # 32 random bytes -> 43 url-safe base64 characters
    token_bytes = secrets.token_bytes(32)
    verifier = base64.urlsafe_b64encode(token_bytes).decode("ascii").rstrip("=")

    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _clean_header_value(value: str, field_name: str) -> str:
    """Validate and normalize a value before placing it in an HTTP header."""
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{field_name} contains HTTP control characters")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty")
    return cleaned


def _clean_bearer_token(value: Any, field_name: str = "access_token") -> str:
    if not isinstance(value, str) or not value or value != value.strip() or any(char.isspace() for char in value):
        raise ValueError(f"{field_name} must be a non-empty token without whitespace")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{field_name} contains HTTP control characters")
    return value


def build_user_agent(client_id: str, contact_email: str, version: str = "1.0.0") -> str:
    """Build GGG-compliant User-Agent header string."""
    client = _clean_header_value(client_id, "client_id")
    contact = _clean_header_value(contact_email, "contact_email")
    release = _clean_header_value(version, "version")
    return f"OAuth {client}/{release} (contact: {contact})"


def get_oauth_status(env: Mapping[str, str] | None = None) -> OAuthStatus:
    """Check whether an access token and public client identifier are configured."""
    e = os.environ if env is None else env
    try:
        raw_client_id = e.get("POE2_CLIENT_ID", "")
        if not isinstance(raw_client_id, str) or raw_client_id != raw_client_id.strip():
            return OAuthStatus.EXTERNALLY_BLOCKED
        client_id = _clean_header_value(raw_client_id, "client_id")
        access_token = _clean_bearer_token(e.get("POE2_ACCESS_TOKEN", ""))
    except (TypeError, ValueError):
        return OAuthStatus.EXTERNALLY_BLOCKED
    if not client_id or not access_token:
        return OAuthStatus.EXTERNALLY_BLOCKED
    return OAuthStatus.CONFIGURED


def _require_ggg_url(url: str, field_name: str, allowed_hosts: frozenset[str]) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        hosts = ", ".join(sorted(allowed_hosts))
        raise ValueError(f"{field_name} must use HTTPS and an approved GGG host ({hosts})")


def _require_local_redirect_uri(redirect_uri: str) -> None:
    parsed = urllib.parse.urlsplit(redirect_uri)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("redirect_uri must target localhost or 127.0.0.1")


def generate_oauth_state() -> str:
    """Generate a CSRF binding value for an authorization request."""
    return secrets.token_urlsafe(32)


def validate_oauth_state(expected: str, received: str) -> bool:
    """Compare the callback state without leaking timing information."""
    return bool(expected) and hmac.compare_digest(expected, received)


@dataclass(frozen=True)
class OAuthToken:
    """Non-persistent token response returned by the authorization-code exchange."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None

    def __post_init__(self) -> None:
        _clean_bearer_token(self.access_token)
        _clean_header_value(self.token_type, "token_type")
        if self.refresh_token is not None:
            _clean_bearer_token(self.refresh_token, "refresh_token")


OAuthTokenTransport = Callable[[str, bytes, dict[str, str], float], Mapping[str, Any]]


def _default_token_transport(url: str, body: bytes, headers: dict[str, str], timeout: float) -> Mapping[str, Any]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, Mapping):
        raise ValueError("OAuth token response must be a JSON object")
    return decoded


def exchange_authorization_code(
    token_url: str,
    client_id: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    contact_email: str = "support@companion.local",
    transport: OAuthTokenTransport | None = None,
    timeout: float = 10.0,
) -> OAuthToken:
    """Exchange an authorization code using the public-client PKCE contract."""
    if not token_url.startswith("https://"):
        raise ValueError("token_url must use HTTPS")
    _require_ggg_url(token_url, "token_url", frozenset({"www.pathofexile.com"}))
    _require_local_redirect_uri(redirect_uri)
    client = _clean_header_value(client_id, "client_id")
    if not code or not redirect_uri or not code_verifier:
        raise ValueError("code, redirect_uri, and code_verifier are required")

    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": client,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
    ).encode("ascii")
    token_payload = (transport or _default_token_transport)(
        token_url,
        body,
        {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": build_user_agent(client, contact_email),
        },
        timeout,
    )
    if not isinstance(token_payload, Mapping):
        raise ValueError("OAuth token response must be a JSON object")
    raw_access_token = token_payload.get("access_token")
    if not isinstance(raw_access_token, str):
        raise ValueError("OAuth token response access_token must be a string")
    access_token = _clean_bearer_token(raw_access_token)
    raw_token_type = token_payload.get("token_type", "Bearer")
    if not isinstance(raw_token_type, str):
        raise ValueError("OAuth token response token_type must be a string")
    raw_refresh_token = token_payload.get("refresh_token")
    if raw_refresh_token is not None and not isinstance(raw_refresh_token, str):
        raise ValueError("OAuth token response refresh_token must be a string")
    expires_in = token_payload.get("expires_in")
    return OAuthToken(
        access_token=access_token,
        token_type=raw_token_type,
        expires_in=int(expires_in) if expires_in is not None else None,
        refresh_token=raw_refresh_token,
    )


def build_authorization_url(
    client_id: str,
    redirect_uri: str,
    scope: str,
    code_challenge: str,
    state: str,
) -> str:
    """Build GGG OAuth authorization endpoint URL with PKCE parameters."""
    _require_ggg_url("https://www.pathofexile.com/oauth/authorize", "authorization_url", frozenset({"www.pathofexile.com"}))
    _require_local_redirect_uri(redirect_uri)
    if not client_id or not code_challenge or not state:
        raise ValueError("client_id, code_challenge, and state are required")
    base_url = "https://www.pathofexile.com/oauth/authorize"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": scope,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{base_url}?{urllib.parse.urlencode(params)}"
