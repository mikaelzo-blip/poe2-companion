# Architectural Design: Milestone 10 — Official API + Deeper PoB2

## Architecture Overview

Milestone 10 introduces structured synchronization with the official Path of Exile 2 Character API and deeper PoB2 comparison:
- `companion/api/oauth.py`: PKCE code challenge generation (RFC 7636), GGG OAuth URL construction, token management, credential status detection (`CONFIGURED`, `EXTERNALLY_BLOCKED`).
- `companion/api/circuit_breaker.py`: `ApiCircuitBreaker` guarding against 4xx responses (401, 403, 429) with exponential cool-down and state machine (`CLOSED`, `OPEN`, `HALF_OPEN`).
- `companion/api/client.py`: GGG-compliant HTTP client enforcing `User-Agent` format (`OAuth {client_id}/1.0.0 (contact: {contact})`) and integrating circuit breaker protection.
- `companion/api/schema.py`: Structured Pydantic models for official API responses: `OfficialCharacterData`, `OfficialItem`, `OfficialQuestStats`.
- `companion/api/pob2_comparator.py`: Deeper PoB2 comparator mapping passive node hashes, calculating build diffs, and detecting game version patch drift (`metadata.version`).
- `companion/api/mock_adapter.py`: Deterministic offline adapter providing reproducible fixtures for local contract execution.

## Safety and Compliance Principles
1. **Zero Input & Non-Invasive**:
   - The API client communicates strictly over HTTPS with GGG's public Web API.
   - It performs zero process memory reading and zero keyboard/mouse automation.
2. **Honest External Blocker Handling**:
   - If `POE2_CLIENT_ID` is absent, the system explicitly reports status `EXTERNALLY_BLOCKED` and suggests setting credentials when available. It never fabricates tokens.
3. **Aggressive Circuit Breaking**:
   - 4xx responses trip egress immediately to prevent rate limiting or temporary IP blocks.
