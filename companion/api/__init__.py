"""PoE2 official API integration, OAuth PKCE, circuit breaker, and PoB2 sync subsystem."""

from companion.api.circuit_breaker import ApiCircuitBreaker, CircuitState
from companion.api.client import ApiResponse, Poe2ApiClient
from companion.api.mock_adapter import create_mock_character
from companion.api.oauth import (
    OAuthStatus,
    OAuthToken,
    build_authorization_url,
    build_user_agent,
    exchange_authorization_code,
    generate_oauth_state,
    generate_pkce_pair,
    get_oauth_status,
    validate_oauth_state,
)
from companion.api.pob2_comparator import (
    Pob2ComparisonResult,
    compare_character_with_pob2,
)
from companion.api.schema import (
    OfficialCharacterData,
    OfficialItem,
    OfficialQuestStats,
)

__all__ = [
    "ApiCircuitBreaker",
    "ApiResponse",
    "CircuitState",
    "OAuthStatus",
    "OAuthToken",
    "OfficialCharacterData",
    "OfficialItem",
    "OfficialQuestStats",
    "Poe2ApiClient",
    "Pob2ComparisonResult",
    "build_authorization_url",
    "build_user_agent",
    "compare_character_with_pob2",
    "create_mock_character",
    "exchange_authorization_code",
    "generate_oauth_state",
    "generate_pkce_pair",
    "get_oauth_status",
    "validate_oauth_state",
]
