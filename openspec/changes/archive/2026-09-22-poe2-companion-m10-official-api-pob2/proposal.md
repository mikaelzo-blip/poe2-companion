# Change Proposal: Milestone 10 — Official API + Deeper PoB2

## Why

To achieve structured character synchronization without screen scraping, Path of Exile 2 provides an official character API accessible via OAuth 2.0 with PKCE. The companion must integrate a robust, compliant API adapter with strict User-Agent headers, 4xx circuit breaking to prevent GGG rate limiting or account blocks, versioned passive hash mapping, structured quest/equipment/skills parsing, and deeper PoB2 metric comparison with patch drift detection. If live OAuth credentials are not provided in the environment, the adapter cleanly marks the live transport as `EXTERNALLY_BLOCKED` while providing 100% testable local/mocked contracts.

## What Changes

1. **OAuth 2.0 + PKCE Contract**:
   - Generates PKCE verifier/challenge pairs (RFC 7636).
   - Generates compliant GGG authorization URLs.
   - Enforces GGG User-Agent formatting (`OAuth {client_id}/1.0.0 (contact: {contact})`).
   - Gracefully reports `EXTERNALLY_BLOCKED` when credentials (`POE2_CLIENT_ID`) are absent, without fabricating credentials.
2. **Resilience & 4xx Circuit Breaker**:
   - `ApiCircuitBreaker`: Tracks 4xx response codes (401, 403, 429), trips to `OPEN` state after threshold consecutive errors, and blocks further egress calls until cool-down expires.
3. **Structured Character API Provider**:
   - Pydantic models for character metadata, allocated passive hashes, equipment, socketed gems, and `quest_stats`.
   - Supports local mock fixtures for deterministic offline testing and live mock injection.
4. **Deeper PoB2 Comparison & Patch Drift**:
   - `compare_pob2_character`: compares synchronized API character passives against target PoB2 build trees.
   - Detects build patch drift when `game_version` or tree revision diverges from guide specification.
5. **CLI Subcommands**:
   - `companion api status`: inspects OAuth readiness, circuit breaker health, and last sync.
   - `companion api sync`: executes character synchronization using official API contract or mock payload.
