# Character State Specification

## Purpose

Provides crash-safe, verified per-character persistent state storage with field-level provenance, conservative character ID safety, Windows cross-process single-writer locking, atomic write staging, and safe rolling backup ordering.

## Requirements

### Requirement: Per-Field Provenance and Semantic Verification
The system SHALL wrap observed character state facts in provenance metadata containing the value, source origin, observation timestamp, semantic verification status, staleness indicator, and evidence references. The verification status SHALL be restricted to semantic states (`VERIFIED`, `CORROBORATED`, `SINGLE_SOURCE`, `STALE`, `UNKNOWN`, `CONFLICTING`) and SHALL NOT use uncalibrated numeric confidence percentages.

#### Scenario: State fact stored with complete provenance
- **WHEN** a state field such as character level or cold resistance is updated with an observation
- **THEN** the stored field records its value, source identifier, timestamp, verification status, staleness trigger, and supporting evidence references

#### Scenario: Semantic verification status assignment
- **WHEN** an observation is recorded with a verification status
- **THEN** the system validates that the status is one of the six allowed semantic values and rejects arbitrary percentage scores

### Requirement: Per-Character Isolated JSON Persistence and Filename Safety
The system SHALL store each character's state in a separate JSON file identified by character ID under `runtime/characters/<char_id>.json`. The store SHALL validate character identifiers against a conservative allowed character ID format (non-empty string matching `^[a-zA-Z0-9_-]{1,64}$`) and SHALL reject any identifier containing path traversal characters, path separators, or invalid symbols by raising `InvalidCharacterIdError`. The system SHALL NOT perform lossy sanitization or silent substitution that could collapse distinct character IDs into identical filenames. The original character ID SHALL remain stored verbatim in the state model. The system SHALL maintain an active character reference file (`runtime/active_character.json`) updated via the same atomic-write primitive.

#### Scenario: Multi-character data isolation
- **WHEN** states for two distinct valid characters are created or updated
- **THEN** each character state is written to its own dedicated file and changes in one do not mutate the other

#### Scenario: Invalid character ID rejected without silent mutation
- **WHEN** a character identifier contains path traversal characters (`..`, `/`, `\`), spaces, or unsupported symbols
- **THEN** the store raises `InvalidCharacterIdError` immediately and refuses to create or load the file

#### Scenario: Collision prevention between distinct IDs
- **WHEN** two distinct character identifiers share similar substrings (e.g. `char_01` vs `char.01` or `char/01`)
- **THEN** invalid IDs are rejected rather than silently sanitized to match `char_01`, preventing filename collision

#### Scenario: Active character pointer resolution
- **WHEN** a character is activated
- **THEN** `runtime/active_character.json` is updated atomically using the atomic write primitive to reference that character's ID and file path

### Requirement: Cross-Process Single-Writer File Locking via `msvcrt.locking`
The system SHALL enforce that exactly one process can write to character runtime state at any time using Windows standard-library file locking (`msvcrt.locking` on `runtime/state.lock`). The locking protocol SHALL:
1. Open or create the lock file and guarantee it contains at least one byte.
2. Seek to byte 0 prior to locking.
3. Acquire an exclusive non-blocking lock on exactly byte 0 using `msvcrt.LK_NBLCK`.
4. Hold the lock file descriptor open for the entire duration of the state mutation transaction (covering serialization, temporary file write, sync, backup copy, atomic replacement, and backup pruning).
5. In a `finally` block, unlock byte 0 and reliably close the file descriptor.
If an exclusive lock cannot be acquired due to another process holding the lock, the operation SHALL fail immediately with `StateLockError` without modifying any state.

#### Scenario: Exclusive writer lock acquisition across transaction
- **WHEN** a writer process begins state modification
- **THEN** it acquires the single-byte non-blocking lock and holds it across the complete write and backup transaction

#### Scenario: Cross-process concurrent writer conflict rejection
- **WHEN** a separate process attempts to acquire the lock while another process is in the middle of a state mutation transaction
- **THEN** the competing process immediately raises `StateLockError` and leaves disk state unaltered

### Requirement: Crash-Safe Atomic Writes and Safe Backup Ordering
The system SHALL persist character state and active character references using a crash-safe atomic write procedure that eliminates crash windows where canonical state is absent. The procedure SHALL:
1. Serialize the new state payload.
2. Write to a temporary file created in the same filesystem directory (`runtime/characters/<char_id>.tmp.<uuid>`).
3. Flush the file buffer and call `os.fsync` on the underlying file descriptor.
4. If a canonical state file already exists and is valid, COPY the current valid canonical file to a timestamped backup (`runtime/backups/<char_id>/state.<timestamp>.bak`) using a safe backup write procedure. The canonical file SHALL NOT be moved or deleted before replacement.
5. Atomically replace the destination canonical file using `os.replace(temp_path, canonical_path)`.
6. Only after successful completion of `os.replace`, prune historical backups exceeding the bounded retention limit (maximum 3 backups).
A corrupted or unreadable canonical state file SHALL NEVER overwrite or displace existing known-good backups.

#### Scenario: Atomic file update leaves canonical file available throughout
- **WHEN** character state is saved to disk
- **THEN** the existing canonical file remains present and accessible until atomically replaced by the synced temporary file

#### Scenario: Interrupted write leaves existing state file intact
- **WHEN** a write operation fails or terminates prior to atomic file replacement (e.g. during serialization, temp write, or backup copy)
- **THEN** the existing canonical state file remains completely intact and uncorrupted, and orphaned temporary files are cleaned up

#### Scenario: Corrupt canonical file does not displace backups
- **WHEN** a state write is initiated while the existing canonical file on disk is corrupt or unreadable
- **THEN** the corrupted file is not copied into backups, preserving valid historical recovery points

#### Scenario: Active character reference uses same atomic-write primitive
- **WHEN** `runtime/active_character.json` is updated
- **THEN** the write is performed via a same-directory temp file, flushed, fsynced, and atomically replaced

### Requirement: Bounded Rolling Backups and Automated Recovery
The system SHALL maintain a bounded rolling backup directory for each character containing at most three valid historical snapshots, and SHALL provide automated recovery from the latest valid backup when the canonical state file is corrupt or unreadable.

#### Scenario: Rolling backup retention limit
- **WHEN** multiple successive state updates occur for a character
- **THEN** at most 3 newest valid backup files are retained in `runtime/backups/<char_id>/`, with older backups pruned after successful replacement

#### Scenario: Automated restoration from valid backup upon corruption
- **WHEN** a character state file cannot be parsed due to file corruption or invalid JSON
- **THEN** the store restores state from the most recent valid backup file

### Requirement: Schema Versioning and Migration Dispatch
The system SHALL validate character state files against a declared schema version (`2.0`) and dispatch registered migrations when encountering valid previous schema versions, rejecting unhandled future versions.

#### Scenario: Valid current schema loaded directly
- **WHEN** a state file with `schema_version: "2.0"` is loaded
- **THEN** the model validates successfully without executing migration handlers

#### Scenario: Upgrading prior schema version
- **WHEN** a state file with an older supported schema version is loaded
- **THEN** the system executes the registered migration sequence to upgrade the payload to the current schema

#### Scenario: Unsupported future schema rejected
- **WHEN** a state file with an unrecognized or future schema version is loaded
- **THEN** loading fails with an unsupported schema version error

### Requirement: Minimal State Management CLI
The system SHALL expose standard-library CLI subcommands to initialize and inspect character state without requiring a background service or database.

#### Scenario: Initialize new character state via CLI
- **WHEN** the user executes the state init command with valid character ID and name arguments
- **THEN** a new isolated character state file is created and set as the active character

#### Scenario: Inspect existing character state via CLI
- **WHEN** the user executes the state inspect command
- **THEN** the system outputs formatted JSON or human-readable summary of the character state and provenance fields

### Requirement: Live Session Tracking Fields
The `CharacterState` domain model SHALL support optional provenanced live tracking fields including `current_zone` (`ProvenancedField[str]`), `death_count` (`ProvenancedField[int]`), `session_active` (`bool`), and `last_observed_at` (`datetime`), allowing the state store to represent real-time gameplay context alongside offline build data.

#### Scenario: Character state holds live session facts
- **WHEN** a character state is initialized or reconciled from live game events
- **THEN** `current_zone`, `death_count`, and `session_active` fields SHALL serialize to and deserialize from state JSON without schema validation errors
