"""Unit tests for Milestone 10 official API schema, client, and mock adapter."""

from io import BytesIO
import pytest
from urllib.error import HTTPError
from companion.api.circuit_breaker import ApiCircuitBreaker
from companion.api.client import Poe2ApiClient
from companion.api.mock_adapter import create_mock_character
from companion.api.client import ApiResponse
from companion.api.schema import OfficialCharacterData, OfficialItem, OfficialQuestStats


def test_official_character_schema() -> None:
    data = create_mock_character(character_id="hero_1", level=55, game_version="0.1.0")
    assert data.character_id == "hero_1"
    assert data.level == 55
    assert len(data.passives) > 0
    assert len(data.equipment) > 0
    assert data.quest_stats.spirit_capacity > 0


def test_official_payload_requires_versioned_metadata() -> None:
    with pytest.raises(ValueError):
        OfficialCharacterData.from_api_payload(
            {
                "character_id": "hero_1",
                "name": "Exile",
                "class": "Mercenary",
                "level": 70,
                "league": "Standard",
            }
        )
    with pytest.raises(ValueError):
        OfficialCharacterData.from_api_payload(
            {
                "name": "Exile",
                "class": "Mercenary",
                "level": 70,
                "league": "Standard",
                "metadata": {"version": "0.1.0"},
            }
        )
    with pytest.raises(ValueError):
        OfficialCharacterData.from_api_payload(
            {
                "character_id": "hero_1",
                "name": None,
                "class": "Mercenary",
                "level": 70,
                "league": "Standard",
                "metadata": {"version": "0.1.0"},
            }
        )
    with pytest.raises(ValueError):
        OfficialCharacterData.from_api_payload(
            {
                "character_id": "hero_1",
                "name": "Exile",
                "class": "Mercenary",
                "level": 70,
                "league": 0,
                "metadata": {"version": "0.1.0"},
            }
        )


def test_client_externally_blocked_without_credentials() -> None:
    client = Poe2ApiClient(client_id=None, contact_email=None)
    data, status = client.sync_character("hero_1")
    assert data is None
    assert "EXTERNALLY_BLOCKED" in status


def test_client_circuit_breaker_blocking() -> None:
    cb = ApiCircuitBreaker(failure_threshold=1, cooldown_seconds=60)
    cb.record_failure(429)  # tripped

    client = Poe2ApiClient(
        client_id="valid_client",
        access_token="valid_token",
        api_url="https://api.pathofexile.com/character",
        contact_email="test@example.com",
        circuit_breaker=cb,
    )
    data, status = client.sync_character("hero_1")
    assert data is None
    assert "CIRCUIT_OPEN" in status


def test_client_mock_injection() -> None:
    mock_data = create_mock_character(character_id="mock_hero", level=60)
    client = Poe2ApiClient(mock_data=mock_data)
    data, status = client.sync_character("mock_hero")
    assert data is not None
    assert data.character_id == "mock_hero"
    assert status == "SYNC_SUCCESS"


def test_client_rejects_malformed_bearer_token() -> None:
    client = Poe2ApiClient(
        client_id="client-id",
        access_token=" token ",
        api_url="https://api.pathofexile.com/character",
    )
    assert client.is_live_configured() is False
    data, status = client.sync_character("hero_2")
    assert data is None
    assert "EXTERNALLY_BLOCKED" in status


def test_client_rejects_non_https_endpoint() -> None:
    client = Poe2ApiClient(
        client_id="client-id",
        access_token="access-token",
        api_url="http://api.pathofexile.com/character",
    )
    data, status = client.sync_character("hero_2")
    assert data is None
    assert "HTTPS" in status


def test_client_rejects_non_ggg_endpoint() -> None:
    client = Poe2ApiClient(
        client_id="client-id",
        access_token="access-token",
        api_url="https://evil.example/character",
    )
    data, status = client.sync_character("hero_2")
    assert data is None
    assert "GGG" in status


def test_client_rejects_response_for_different_character() -> None:
    payload = {
        "character_id": "other-character",
        "name": "Exile",
        "class": "Mercenary",
        "level": 70,
        "league": "Standard",
        "metadata": {"version": "0.1.0"},
    }
    client = Poe2ApiClient(
        client_id="client-id",
        access_token="access-token",
        api_url="https://api.pathofexile.com/character",
        transport=lambda *_args: ApiResponse(status_code=200, headers={}, payload=payload),
    )
    data, status = client.sync_character("requested-character")
    assert data is None
    assert "character_id" in status


def test_transport_error_breaks_4xx_sequence() -> None:
    breaker = ApiCircuitBreaker(failure_threshold=2, cooldown_seconds=60)
    breaker.record_failure(429)
    client = Poe2ApiClient(
        client_id="client-id",
        access_token="access-token",
        api_url="https://api.pathofexile.com/character",
        circuit_breaker=breaker,
        transport=lambda *_args: (_ for _ in ()).throw(OSError("offline")),
    )
    data, status = client.sync_character("hero_2")
    assert data is None
    assert "TRANSPORT_ERROR" in status
    assert breaker.consecutive_failures == 0


def test_default_transport_malformed_200_resets_breaker_and_rejects_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"not-json"

    monkeypatch.setattr("companion.api.client._open_url", lambda *_args, **_kwargs: Response())
    breaker = ApiCircuitBreaker(failure_threshold=3, cooldown_seconds=60)
    breaker.record_failure(429)
    client = Poe2ApiClient(
        client_id="client-id",
        access_token="access-token",
        api_url="https://api.pathofexile.com/character",
        circuit_breaker=breaker,
    )

    data, status = client.sync_character("hero_2")

    assert data is None
    assert "INVALID_RESPONSE" in status
    assert breaker.consecutive_failures == 0


def test_default_transport_malformed_429_still_trips_breaker(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_http_error(*_args: object, **_kwargs: object) -> None:
        raise HTTPError(
            "https://api.pathofexile.com/character",
            429,
            "rate limited",
            {},
            BytesIO(b"not-json"),
        )

    monkeypatch.setattr("companion.api.client._open_url", raise_http_error)
    breaker = ApiCircuitBreaker(failure_threshold=1, cooldown_seconds=60)
    client = Poe2ApiClient(
        client_id="client-id",
        access_token="access-token",
        api_url="https://api.pathofexile.com/character",
        circuit_breaker=breaker,
    )

    data, status = client.sync_character("hero_2")

    assert data is None
    assert "HTTP_429" in status
    assert breaker.state.value == "OPEN"


def test_client_success_resets_breaker_before_payload_validation() -> None:
    breaker = ApiCircuitBreaker(failure_threshold=3, cooldown_seconds=60)
    breaker.record_failure(429)

    client = Poe2ApiClient(
        client_id="client-id",
        access_token="access-token",
        api_url="https://api.pathofexile.com/character",
        circuit_breaker=breaker,
        transport=lambda *_args: ApiResponse(status_code=200, headers={}, payload={"invalid": True}),
    )
    data, status = client.sync_character("hero_2")

    assert data is None
    assert "INVALID_RESPONSE" in status
    assert breaker.consecutive_failures == 0


def test_client_fetches_and_parses_official_payload_with_headers() -> None:
    seen: dict[str, object] = {}

    def transport(url: str, headers: dict[str, str], timeout: float) -> ApiResponse:
        seen.update(url=url, headers=headers, timeout=timeout)
        return ApiResponse(
            status_code=200,
            headers={},
            payload={
                "character_id": "hero_2",
                "name": "Exile",
                "class": "Mercenary",
                "level": 72,
                "league": "Standard",
                "metadata": {"version": "0.1.0", "passive_tree_revision": "tree-1"},
                "passives": ["node_a"],
                "equipment": [],
                "quest_stats": {"permanent_passives": 2, "spirit_capacity": 40},
            },
        )

    client = Poe2ApiClient(
        client_id="client-id",
        access_token="access-token",
        contact_email="dev@example.com",
        api_url="https://api.pathofexile.com/character",
        transport=transport,
    )
    data, status = client.sync_character("hero_2")

    assert status == "SYNC_SUCCESS"
    assert data is not None
    assert data.class_name == "Mercenary"
    assert data.passive_tree_revision == "tree-1"
    assert seen["url"] == "https://api.pathofexile.com/character?character_id=hero_2"
    assert seen["headers"] == {
        "Authorization": "Bearer access-token",
        "User-Agent": "OAuth client-id/1.0.0 (contact: dev@example.com)",
        "Accept": "application/json",
    }


def test_client_records_4xx_responses_and_stops_after_threshold() -> None:
    responses = [
        ApiResponse(status_code=429, headers={"Retry-After": "12"}, payload={}),
        ApiResponse(status_code=429, headers={}, payload={}),
    ]

    def transport(url: str, headers: dict[str, str], timeout: float) -> ApiResponse:
        return responses.pop(0)

    breaker = ApiCircuitBreaker(failure_threshold=2, cooldown_seconds=60)
    client = Poe2ApiClient(
        client_id="client-id",
        access_token="access-token",
        api_url="https://api.pathofexile.com/character",
        transport=transport,
        circuit_breaker=breaker,
    )

    _, first_status = client.sync_character("hero_2")
    _, second_status = client.sync_character("hero_2")
    _, third_status = client.sync_character("hero_2")

    assert "HTTP_429" in first_status
    assert "HTTP_429" in second_status
    assert "CIRCUIT_OPEN" in third_status
    assert breaker.consecutive_failures == 2
