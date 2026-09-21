# Proposal

## Why

Path of Exile 2 players currently rely on static, offline character state checkpoints to receive objective recommendations. To provide timely, non-intrusive assistance during active play, the companion requires safe live session awareness. This change introduces process presence detection, a strictly read-only `Client.txt` log tailer, a decoupled observation event bus, a deterministic per-field provenance state reconciler, and an append-only journey history log.

This enables the companion to observe game session transitions, zone entries, level-up milestones, and death events in real time without sending inputs, polling unsafe APIs, or risking private chat exposure.

## What Changes

- Add process-presence monitoring (`companion/sensing/process_presence.py`) detecting game status (`IDLE`, `RUNNING`, `TERMINATED`) across supported executable names (`PathOfExileSteam.exe`, `PathOfExile.exe`) without elevated privileges or third-party hooks.
- Add read-only, stream-safe `Client.txt` tailer (`companion/sensing/client_log.py`) supporting chunked line processing, incomplete trailing lines, file rotation detection, and session discontinuity handling.
- Enforce strict privacy log filtering (Section 6.1): parse only recognized patterns (zone entries, level-ups, deaths) while immediately dropping whispers, guild, global, and party chat without storing or transmitting them.
- Introduce an in-memory observation bus (`companion/observations/schema.py`, `companion/observations/bus.py`) with typed event subscriptions and deterministic ordering.
- Add live state reconciliation (`companion/state/reconciliation.py`) that applies incoming observations to `CharacterState` using `ProvenancedField` metadata and staleness tracking (`companion/state/staleness.py`).
- Implement an append-only, privacy-sanitized journey history logger (`companion/state/history.py`) persisting to `runtime/journey_history.jsonl`.
- Add CLI subcommands (`companion session status`, `companion session tail`, `companion journey list`) for inspecting active session events and historical milestones.

## Capabilities

### New Capabilities
- `session-monitoring`: Process presence detection and read-only Client.txt tailer with rotation safety and privacy filtering.
- `state-reconciliation`: Decoupled observation bus, provenanced state reconciliation, staleness calculation, and journey history logging.

### Modified Capabilities
- `character-state`: Extend character state schema with provenanced live session tracking fields (`current_zone`, `death_count`, `session_active`, `last_observed_at`).

## Impact

- Extends `companion/state/schema.py` with optional live session tracking fields while preserving 3.0 backward compatibility.
- Adds packages `companion/sensing/`, `companion/observations/`, and modules `companion/state/reconciliation.py`, `companion/state/staleness.py`, and `companion/state/history.py`.
- Expands `companion/cli.py` with `session` and `journey` subcommands.
- Zero dependencies added outside Python standard library and Pydantic.
