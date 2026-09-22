# official-api-pob2 Specification

## Purpose

Defines the official PoE2 Character API synchronization subsystem, public OAuth 2.0 PKCE client contract, 4xx circuit breaker, structured character data parsing, and deeper PoB2 metric comparison with patch drift detection.

## Requirements

### Requirement: Public OAuth 2.0 with PKCE and User-Agent Enforcement
The system SHALL implement RFC 7636 PKCE code challenge generation and enforce GGG-compliant User-Agent header formatting for all outbound API communication.

#### Scenario: Generate PKCE challenge
- **WHEN** initiating an OAuth authorization sequence
- **THEN** the client generates a high-entropy cryptographically secure verifier and corresponding base64url-encoded SHA-256 challenge

#### Scenario: GGG User-Agent format enforcement
- **WHEN** an HTTP request header is constructed
- **THEN** the `User-Agent` header follows the GGG compliant format `OAuth {client_id}/1.0.0 (contact: {contact})`

#### Scenario: Missing credentials reported as externally blocked
- **WHEN** live API synchronization is requested without `POE2_CLIENT_ID` or OAuth credentials
- **THEN** the adapter returns status `EXTERNALLY_BLOCKED` without fabricating mock credentials or crashing

### Requirement: 4xx Circuit Breaker Protection
The system SHALL track consecutive 4xx response codes (401, 403, 429) and trip into an `OPEN` state to prevent account bans and rate-limit violations.

#### Scenario: Circuit breaker trips after threshold 4xx errors
- **WHEN** three consecutive requests return 4xx status codes
- **THEN** the circuit breaker trips to `OPEN`, immediately rejecting subsequent calls until the recovery timeout expires

#### Scenario: Circuit breaker resets on successful response
- **WHEN** a request succeeds with status 200 OK
- **THEN** consecutive failure counters reset to zero and the circuit breaker remains `CLOSED`

### Requirement: Structured Character API Ingestion
The system SHALL parse official PoE2 character payloads into structured models containing character metadata, allocated passive hashes, equipped gear, and permanent quest statistics.

#### Scenario: Parse official character payload
- **WHEN** an official character JSON payload is received
- **THEN** the client extracts character level, class, passive tree node hashes, equipment items, and permanent quest attributes into a typed `OfficialCharacterData` model

### Requirement: Deeper PoB2 Comparison and Patch Drift Detection
The system SHALL compare synchronized API character state against PoB2 target build trees and detect version/patch drift.

#### Scenario: Detect build patch drift
- **WHEN** the game metadata version or passive tree revision differs from the target PoB2 guide version
- **THEN** the comparison flags a `PATCH_DRIFT` warning detailing the version mismatch

#### Scenario: Compare allocated passive tree nodes
- **WHEN** comparing synchronized passive node hashes against the target build variant
- **THEN** the system outputs missing, matching, and extraneous passive nodes
