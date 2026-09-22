"""Compliant PoE2 official API client with circuit breaking and honest credential status."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from companion.api.circuit_breaker import ApiCircuitBreaker
from companion.api.oauth import build_user_agent
from companion.api.schema import OfficialCharacterData


@dataclass(frozen=True)
class ApiResponse:
    """Transport-neutral HTTP response used by the client and deterministic tests."""

    status_code: int
    headers: Mapping[str, str]
    payload: Mapping[str, Any]


Transport = Callable[[str, dict[str, str], float], ApiResponse]


def _is_clean_text(value: object, *, token: bool = False) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    return not token or not any(char.isspace() for char in value)


def _decode_payload(raw: bytes) -> Mapping[str, Any]:
    if not raw:
        return {}
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(decoded, Mapping):
        return {}
    return decoded


class _NoRedirectHandler(HTTPRedirectHandler):
    """Prevent urllib from forwarding bearer credentials to another origin."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        raise OSError("redirects are not allowed for credentialed API requests")


def _open_url(request: Request, timeout: float) -> Any:
    return build_opener(_NoRedirectHandler()).open(request, timeout=timeout)


def _urllib_transport(url: str, headers: dict[str, str], timeout: float) -> ApiResponse:
    """Perform one read-only HTTPS request using the standard library."""
    request = Request(url, headers=headers, method="GET")
    try:
        with _open_url(request, timeout=timeout) as response:
            return ApiResponse(
                status_code=response.status,
                headers=dict(response.headers.items()),
                payload=_decode_payload(response.read()),
            )
    except HTTPError as error:
        try:
            payload = _decode_payload(error.read())
        finally:
            error.close()
        return ApiResponse(
            status_code=error.code,
            headers=dict(error.headers.items()),
            payload=payload,
        )
    except URLError as error:
        raise OSError(f"official API transport failed: {error.reason}") from error


class Poe2ApiClient:
    """Read-only client for official Path of Exile 2 Character API payloads."""

    def __init__(
        self,
        client_id: str | None = None,
        access_token: str | None = None,
        contact_email: str | None = None,
        api_url: str | None = None,
        circuit_breaker: ApiCircuitBreaker | None = None,
        mock_data: OfficialCharacterData | None = None,
        transport: Transport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.client_id = client_id if client_id is not None else os.environ.get("POE2_CLIENT_ID", "")
        self.access_token = access_token if access_token is not None else os.environ.get("POE2_ACCESS_TOKEN", "")
        self.contact_email = contact_email or os.environ.get("POE2_CONTACT_EMAIL", "support@companion.local")
        self.api_url = api_url if api_url is not None else os.environ.get("POE2_API_URL", "")
        self.circuit_breaker = circuit_breaker or ApiCircuitBreaker()
        self.mock_data = mock_data
        self.transport = transport or _urllib_transport
        self.timeout = timeout

    def is_live_configured(self) -> bool:
        """Return whether credentials and the approved GGG API origin are present."""
        parsed = urlsplit(self.api_url)
        return bool(
            _is_clean_text(self.client_id)
            and _is_clean_text(self.access_token, token=True)
            and parsed.scheme == "https"
            and parsed.hostname == "api.pathofexile.com"
        )

    def sync_character(self, character_id: str) -> tuple[OfficialCharacterData | None, str]:
        """Synchronize character data via official API or injected mock fixture."""
        if self.mock_data is not None:
            return self.mock_data, "SYNC_SUCCESS"

        if not _is_clean_text(self.client_id) or not _is_clean_text(self.access_token, token=True):
            return None, "EXTERNALLY_BLOCKED: OAuth credentials are missing or malformed"
        if not isinstance(self.api_url, str) or not self.api_url.strip():
            return None, "EXTERNALLY_BLOCKED: OAuth token and POE2_API_URL are not configured"
        if not self.api_url.lower().startswith("https://"):
            return None, "CONFIG_ERROR: POE2_API_URL must use HTTPS"
        if urlsplit(self.api_url).hostname != "api.pathofexile.com":
            return None, "CONFIG_ERROR: POE2_API_URL must target the approved GGG API origin"

        if not self.circuit_breaker.can_execute():
            return None, f"CIRCUIT_OPEN: 4xx failure limit reached (last status: {self.circuit_breaker.last_failure_status})"

        try:
            user_agent = build_user_agent(self.client_id, self.contact_email)
            separator = "&" if "?" in self.api_url else "?"
            url = f"{self.api_url}{separator}{urlencode({'character_id': character_id})}"
            response = self.transport(
                url,
                {
                    "Authorization": f"Bearer {self.access_token}",
                    "User-Agent": user_agent,
                    "Accept": "application/json",
                },
                self.timeout,
            )
        except (OSError, ValueError) as error:
            self.circuit_breaker.record_success()
            return None, f"TRANSPORT_ERROR: {error}"

        if response.status_code == 200:
            self.circuit_breaker.record_success()
            try:
                character = OfficialCharacterData.from_api_payload(response.payload, character_id=character_id)
            except (TypeError, ValueError) as error:
                return None, f"INVALID_RESPONSE: {error}"
            return character, "SYNC_SUCCESS"

        if response.status_code in self.circuit_breaker.TARGETED_4XX:
            self.circuit_breaker.record_failure(response.status_code)
        else:
            self.circuit_breaker.record_success()
        return None, f"HTTP_{response.status_code}: official API request failed"
