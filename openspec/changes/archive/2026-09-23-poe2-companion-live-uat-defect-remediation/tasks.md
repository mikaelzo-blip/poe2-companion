# Tasks

## 1. P0 Remediation: Provenance-Preserving Gear Conflict Evaluation

- [x] 1.1 Implement verified attribute extraction helper in `companion/gear/conflicts.py` that checks explicit typed provenance metadata (`ProvenancedField`, `OperandEvidence`), verifies `VERIFIED` state and freshness, and rejects raw numeric values (`int`/`float`) and default-zero coercion
- [x] 1.2 Migrate legacy unit test fixtures in `tests/gear/test_evaluator_and_conflicts.py`, `tests/test_m8_integration.py`, and `tests/test_m9_integration.py` to provide explicit verified evidence containers (`ProvenancedField` or `OperandEvidence`)
- [x] 1.3 Update `handle_gear_status` in `companion/cli.py` to retrieve the active character's attributes from `CharacterStateStore` and pass them to `detect_mechanic_conflicts`, and verify with CLI execution tests
- [x] 1.4 Add unit tests in `tests/gear/test_evaluator_and_conflicts.py` asserting that raw ints, missing attributes, and UNKNOWN/STALE attributes evaluate to insufficient evidence and do not emit factual unmet requirement conflicts

## 2. P1 Remediation: Client Log Tailer Bounded Incremental Reading & Binary Decoding Contract

- [x] 2.1 Refactor `ClientLogTailer.poll()` in `companion/sensing/client_log.py` to use binary line-bounded reading (`"rb"`) with strict byte offsets and UTF-8 replacement decoding (`errors="replace"`)
- [x] 2.2 Add unit tests in `tests/sensing/test_client_log.py` verifying non-ASCII text, malformed/undecodable bytes, and confirming malformed lines safely return None without corrupting offsets or skipping subsequent valid events
- [x] 2.3 Add unit tests in `tests/sensing/test_client_log.py` verifying backlog processing (>1,000 lines) across consecutive polls without dropping or duplicating lines
- [x] 2.4 Add unit tests in `tests/sensing/test_client_log.py` verifying partial trailing byte line handling, file rotation/truncation resets, and file growth between polls

## 3. P1 Remediation: PoE2 Level-Up Regex and Parser Extension

- [x] 3.1 Update `_LEVEL_UP_RE` in `companion/sensing/client_log.py` to support optional parenthetical class tokens (e.g. `: BOMSHAK (Mercenary) is now level 11`) and extract `character_class` when present
- [x] 3.2 Add unit tests in `tests/sensing/test_client_log.py` testing PoE2 class-token level-up lines, legacy level-up lines, and chat rejection

## 4. Repository Hygiene & Real-Log Regression Testing

- [x] 4.1 Create sanitized real-log regression test suite in `tests/sensing/test_real_log_regression.py` validating 49-style level-ups, large batch tailing, and chat privacy filtering using minimal synthetic fixtures
- [x] 4.2 Update `.gitignore` to comprehensively ignore `runtime/` (preventing tracking of `journey_history.jsonl` and runtime state) while preserving any intentionally tracked templates
- [x] 4.3 Sanitize local paths and non-essential real character identifiers from `docs/audits/LIVE_UAT_V01.md` before commit

## 5. Verification and Operational Acceptance Gate

- [x] 5.1 Run full project test suite with `uv run pytest -W error` and verify all tests pass with zero warnings
- [x] 5.2 Run anti-cheat input compliance check with `uv run pytest tests/compliance/test_no_input_guard.py -v` and verify zero input simulation symbols
- [x] 5.3 Run byte-compilation validation with `uv run python -m compileall -q companion tests` and check for syntax errors
- [x] 5.4 Run git whitespace and diff check with `git diff --check`
- [x] 5.5 Perform read-only operational check against real `Client.txt` ensuring backlog polling does not skip lines and level-ups parse correctly without modifying the file
