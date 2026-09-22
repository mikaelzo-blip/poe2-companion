# Proposal

## Why

During the first live operational acceptance test (`LIVE_UAT_V01`) against a real Path of Exile 2 installation and real `Client.txt` log files, three production defects were discovered:
1. P0: Unobserved/UNKNOWN character attributes were coerced to numeric `0` in `companion/gear/conflicts.py` and gear CLI commands, emitting false factual unmet attribute warnings (`"observed character has 0 Str"`), violating the project's core provenance rules.
2. P1: `ClientLogTailer.poll(max_lines=1000)` advanced the file offset to EOF upon reading a chunk, but iterated only `lines[:max_lines]`, permanently skipping lines 1,001 through EOF on large log files.
3. P1: PoE2 level-up log lines containing class tokens (e.g. `: BOMSHAK (Mercenary) is now level 11`) failed to match the level-up regex, ignoring 49 observed level-up events in the real client log.

Remediating these three defects now ensures that gear conflict evaluation preserves uncertainty without fabricating zero-value stats, that unprovenanced values are never treated as verified facts, and that local client log streaming processes backlogs completely without event loss, crash, or offset corruption.

## What Changes

- **Provenance-Preserving Mechanical Conflict Evaluation**:
  - Eliminate `.get(..., 0)` and default-zero coercion for character attributes in `companion/gear/conflicts.py`.
  - Enforce that mechanical attribute requirement evaluation emits factual unmet requirement conflicts ONLY when both the required attribute and the character's observed attribute are `VERIFIED` via explicit typed provenance metadata (`ProvenancedField` or `OperandEvidence`).
  - Explicitly reject plain numeric values (`int`, `float`) as verified evidence: unprovenanced values evaluate to `UNKNOWN` / insufficient evidence.
  - If character attributes are `UNKNOWN`, `STALE`, unprovenanced, missing, or unverified, evaluate attribute satisfaction to `UNKNOWN`/`INSUFFICIENT_EVIDENCE` and suppress factual unmet requirement conflicts.
  - Wire character state attribute lookup into `handle_gear_status` in `companion/cli.py` while respecting provenance states.
  - Migrate legacy unit test fixtures passing raw integers to supply explicit verified evidence containers (`ProvenancedField` or `OperandEvidence`) rather than weakening production semantics.

- **Bounded Incremental Log Tailer Offset Management & Binary Decoding Contract**:
  - Refactor `ClientLogTailer.poll(max_lines=N)` to use binary reading (`"rb"`) with strict byte offsets, advancing only through the end of complete lines (`b"\n"`) actually consumed.
  - Define an explicit binary decoding contract: complete byte lines are decoded using UTF-8 with replacement (`errors="replace"`), guaranteeing that malformed or undecodable byte sequences do not crash the tailer, corrupt byte offsets, or make subsequent valid events disappear.
  - Retain unconsumed lines or byte positions for subsequent `poll()` invocations, ensuring that backlogs exceeding `max_lines` are processed across consecutive polls without skipping or duplicating events.
  - Incomplete trailing byte lines remain unread in the file until completed by subsequent writes.
  - Preserve read-only access to `Client.txt`, trailing incomplete line buffering, rotation/truncation detection, and strict chat privacy filtering.

- **PoE2 Level-Up Parser Class Token Support**:
  - Extend level-up regex in `companion/sensing/client_log.py` to match the real PoE2 format (`: <CharacterName> (<ClassName>) is now level <Level>`) while retaining backward compatibility with the legacy format (`: <CharacterName> is now level <Level>`).
  - Extract character name, optional class token, and level without inventing unverified class mappings.
  - Ensure the parser strictly ignores chat, whispers, and unrelated system lines.

- **Real-Log Sanitized Regression Testing & Repository Hygiene**:
  - Add minimal, sanitized test fixtures reflecting observed real-log patterns (49-style level-ups, multi-thousand-line backlogs, non-ASCII/malformed bytes, truncation, rotation, and chat filtering) without committing full user log files.
  - Sanitize `docs/audits/LIVE_UAT_V01.md` before commit by removing unnecessary personal/local identifiers (machine-specific paths, non-essential player character names) while preserving technical findings.
  - Plan an implementation task to comprehensively ignore `runtime/` in `.gitignore` (preventing tracking of `journey_history.jsonl` and runtime state) while preserving any intentionally tracked templates, without editing `.gitignore` during planning.

## Capabilities

### New Capabilities
- `provenance-preserving-mechanical-conflicts`: Factual, provenance-preserving requirement checking for gear mechanical conflicts that treats unobserved and unprovenanced attributes as `UNKNOWN`/`INSUFFICIENT_EVIDENCE` rather than numeric zero or verified facts.
- `client-log-streaming`: Non-dropping, byte-offset-bounded client log stream processing and regex parsing supporting PoE2 class-token level-up entries, large backlogs, and robust binary decoding.

### Modified Capabilities
<!-- None. Existing capability specs remain unmodified; behavioral extensions are specified in the new capability deltas. -->

## Impact

- **Affected Code**:
  - `companion/gear/conflicts.py`: Attribute lookup, provenance verification helper, and requirement comparison logic.
  - `companion/cli.py`: Attribute passing in `handle_gear_status`.
  - `companion/sensing/client_log.py`: `_LEVEL_UP_RE` regex, binary reading, and `ClientLogTailer.poll()` byte-offset management.
  - `tests/gear/test_evaluator_and_conflicts.py`, `tests/sensing/test_client_log.py`, `tests/test_m5_integration.py`, `tests/test_m8_integration.py`, `tests/test_m9_integration.py`: Unit, fixture migration, and regression test suites.
- **APIs & Dependencies**: No external API changes, no new package dependencies, no schema breaking changes.
- **Operational Guardrails**: Read-only access to `Client.txt` preserved; no background daemon or continuous runtime introduced; `runtime/` strictly ignored.
