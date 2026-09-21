# Design

## Context

See proposal.md for motivation and high-level requirements. The companion currently maintains offline state (`CharacterState`), computes build deltas (M2), evaluates guide rules and level-52 weapon swaps (M3), and ranks player objectives (M4). To transition into an active companion assistant, the runtime needs to detect when Path of Exile 2 is running and stream events from `Client.txt` without invasive process injection, keyboard hooks, or memory reading.

## Goals / Non-Goals

**Goals:**
- Provide a non-invasive, read-only process monitor detecting game state transitions.
- Safely tail `Client.txt` handling partial lines, chunked reads, log rotation, and session gaps.
- Enforce a strict privacy boundary that drops all player chat (whispers, guild, local, trade, global).
- Decouple sensing monitors from state updates via an in-memory observation event bus.
- Reconcile incoming game events into `CharacterState` using per-field provenance and staleness tracking.
- Record structured milestones into an append-only `journey_history.jsonl` log.

**Non-Goals:**
- Memory injection, hooking game threads, reading private process memory, or automating any keystrokes/mouse clicks.
- Parsing player chat or storing sensitive in-game communication.
- Real-time HUD overlay or screen overlays (handled separately or deferred).

## Decisions

### 1. Standard-Library Process Inspection vs Third-Party psutil
- **Decision**: Use standard library process inspection via `tasklist` / `wmic` / `/proc` / PowerShell depending on platform, encapsulated behind an abstract `ProcessDetector` protocol.
- **Rationale**: Keeps dependencies minimal and avoids native C-extension compilation issues across environments.
- **Alternatives Considered**: `psutil` (adds external C binary dependency); Windows API ctypes calls (platform locked and brittle).

### 2. Read-Only Chunked Tailer with Inode / Size Reset Detection
- **Decision**: Tailer opens `Client.txt` with `open(..., "r", encoding="utf-8", errors="replace")` in read-only mode, tracks `tell()` byte offset, buffers partial trailing lines until `\n`, and compares current file size against previous offset to detect file rotation or truncation.
- **Rationale**: Windows logs can rotate or be cleared when launching new client sessions; detecting size shrinkage resets the offset to 0 cleanly without missing subsequent lines or crashing.
- **Alternatives Considered**: Shelling out to `Get-Content -Wait` or `tail -f` (subprocesses harder to unit test and leak handles).

### 3. Strict Regex-Based Event Whitelist & Chat Drop Invariant
- **Decision**: Match log lines against explicit pre-compiled regular expressions:
  - Zone generation: `r': Generating level (?P<level>\d+) area "(?P<zone>[^"]+)"'`
  - Zone entrance: `r': Entered area "(?P<zone>[^"]+)"'`
  - Level-up: `r': (?P<char>[a-zA-Z0-9_-]+) is now level (?P<level>\d+)'`
  - Death: `r': (?P<char>[a-zA-Z0-9_-]+) has been slain'`
  Any line containing chat prefixes (`@From`, `@To`, `$`, `#`, `%`) is immediately dropped without parsing.
- **Rationale**: Satisfies Blueprint Section 6.1 and guarantees zero leakage of private conversation to disk or telemetry.

### 4. Decoupled Observation Event Bus
- **Decision**: Implement a lightweight in-memory `ObservationBus` with `subscribe(event_type, callback)` and `publish(event)`.
- **Rationale**: Allows multiple listeners (state reconciler, notification engine in M6, journey logger) to react to game events independently without tight coupling.

### 5. Append-Only Journey History (`journey_history.jsonl`)
- **Decision**: Write normalized event records (`timestamp`, `character_id`, `event_type`, `payload`) to `runtime/journey_history.jsonl` using append mode (`"a"`).
- **Rationale**: Crash-proof and easy to parse or stream for session recaps (M6).

## Risks / Trade-offs

- **[Risk]** Log line encoding variations (e.g. non-ASCII zone names or player names) → **Mitigation**: Open log files with `errors="replace"` and UTF-8 encoding.
- **[Risk]** Fast log spamming during map loading → **Mitigation**: Tailer buffers lines in batches up to 500 lines per poll cycle.
- **[Risk]** Character name mismatch in party play (another player levels up or dies) → **Mitigation**: Match event character name against active `CharacterState.character_id` / `name` before mutating state.
