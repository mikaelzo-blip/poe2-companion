# Live UAT Defect Remediation Acceptance Report

**Execution Date**: 2026-09-22
**Baseline Planning Commit SHA**: `4de58792b82ca94c0652f2ac079da3db6ed2f5e2` (`4de5879`)
**Host Environment**: Windows 11 (AMD64), Python 3.11.16, `uv` managed virtualenv
**Scope**: Verification and operational acceptance of fixes for three live UAT defects plus repository hygiene under OpenSpec change `poe2-companion-live-uat-defect-remediation`.

---

## 1. Planning Commit SHA
- **Planning Commit**: `4de58792b82ca94c0652f2ac079da3db6ed2f5e2`
- **Message**: `plan: remediate live UAT defects`
- **Scope**: OpenSpec proposal, design, specs, tasks for `poe2-companion-live-uat-defect-remediation`.

---

## 2. Implementation Files Changed
- `companion/gear/conflicts.py`:
  - Implemented `_extract_verified_attribute()` to extract integer attribute values requiring explicit typed provenance metadata (`ProvenancedField`, `OperandEvidence`), verifying `VERIFIED` state, freshness, and rejecting raw numeric values (`int`/`float`) and default-zero coercion.
  - Required `item.verification == VerificationState.VERIFIED` before checking attribute deficits.
  - Eliminated `.get(..., 0)` default-zero attribute coercion.
- `companion/cli.py`:
  - Updated `handle_gear_status()` to retrieve the character's provenanced attributes from `CharacterStateStore` and pass `character_attributes=char_attrs` to `detect_mechanic_conflicts()`.
- `companion/sensing/client_log.py`:
  - Refactored `ClientLogTailer.poll()` to open log files in binary mode (`"rb"`), track exact consumed byte offsets, and decode complete byte lines using UTF-8 replacement decoding (`errors="replace"`).
  - Ensured incomplete trailing byte lines remain unread until completed.
  - Updated `_LEVEL_UP_RE` and `parse_log_line()` to parse PoE2 parenthetical class tokens (e.g. `: Character (Class) is now level Lvl`) while preserving support for legacy lines without class tokens.
- `tests/gear/test_evaluator_and_conflicts.py`:
  - Migrated legacy test fixtures to supply `ProvenancedField` with `VerificationState.VERIFIED`.
  - Added unit tests for rejection of raw numeric values (`{"str": 0}`, `{"str": 40}`), suppression of unmet conflicts when attributes are UNKNOWN or STALE, suppression when item requirements are unverified, and factual conflict emission when both operands are verified.
- `tests/cli/test_m8_cli.py`:
  - Added `test_gear_status_cli_provenance_preservation()` verifying that unobserved attributes produce zero false unmet conflicts, and verified deficits produce factual conflicts.
- `tests/test_m8_integration.py`:
  - Migrated attribute fixtures to `ProvenancedField`.
- `tests/sensing/test_client_log.py`:
  - Added unit tests for backlog processing (>1,000 lines across consecutive polls), binary decoding / malformed byte resilience, and trailing partial byte line growth.
  - Added unit tests for PoE2 class-token level-up parsing and chat rejection.
- `tests/sensing/test_real_log_regression.py`:
  - Added sanitized regression test suite validating 49-style level-ups, multi-batch tailing, and privacy filtering.
- `openspec/changes/poe2-companion-live-uat-defect-remediation/tasks.md`:
  - Marked all 18 tasks complete.

---

## 3. Repository Hygiene & .gitignore
- **`.gitignore` Update**:
  - Replaced fragmented rules (`runtime/characters/`, `runtime/backups/`, `runtime/*.lock`, `runtime/*.json`) with an anchored `/runtime/` rule.
  - Excludes `runtime/journey_history.jsonl` and all local state from git tracking while preserving clean working tree.
- **`docs/audits/LIVE_UAT_V01.md` Sanitization**:
  - Replaced machine-specific path `E:\SteamLibrary\steamapps\common\Path of Exile 2\logs\Client.txt` with `<PoE2_Install_Dir>/logs/Client.txt`.
  - Replaced real character names with generic placeholders (`<CharacterName>`, `Character_Exile`).
  - Verified 0 private chat lines, 0 credentials, 0 tokens.

---

## 4. Exact Defect Fixes

### A. P0 — UNKNOWN_COERCED_TO_ZERO
- **Root Cause**: `attrs.get("str", 0)` defaulted missing/unobserved attributes to numeric 0.
- **Remediation**:
  - `_extract_verified_attribute` strictly checks provenance containers (`ProvenancedField`, `OperandEvidence`).
  - Raw integers and floats evaluate to `None` (insufficient evidence / UNKNOWN).
  - Both character attribute and item requirement must have `VERIFIED` state to emit factual `UNMET_ATTRIBUTE`.
  - No fallback to 0.

### B. P1 — CLIENT_LOG_TAILER_CHUNK_TRUNCATION
- **Root Cause**: `ClientLogTailer.poll()` advanced `self._offset = f.tell()` to EOF while only iterating `lines[:max_lines]`.
- **Remediation**:
  - Opened in binary mode (`"rb"`).
  - Offset advances strictly line-by-line via `last_consumed_offset = f.tell()`.
  - Offset is committed only for complete newline-terminated lines actually consumed.
  - Backlog lines beyond `max_lines` remain available for subsequent polls.

### C. P1 — POE2_LEVEL_UP_CLASS_TOKEN_MISMATCH
- **Root Cause**: `_LEVEL_UP_RE` expected `:<char> is now level <lvl>` without optional class tokens.
- **Remediation**:
  - Updated pattern: `r':\s+(?P<char>[a-zA-Z0-9_\u00C0-\u017F-]+)(?:\s+\((?P<class>[a-zA-Z0-9_\s-]+)\))?\s+is now level\s+(?P<level>\d+)'`.
  - Populates optional `character_class` payload field when present.

---

## 5. Test Suite Verification & Quality Gates

| Check | Command | Result |
|---|---|---|
| **Full Test Suite** | `uv run pytest -W error` | **464 passed**, 0 warnings (2.98s) |
| **Input Simulation Compliance** | `uv run pytest tests/compliance/test_no_input_guard.py -v` | **10 passed**, 0 violations |
| **Byte-compilation** | `uv run python -m compileall -q companion tests` | **Clean**, 0 syntax/compilation errors |
| **Git Diff Whitespace Check** | `git diff --check` | **Clean**, 0 whitespace/EOF errors |
| **OpenSpec Strict Validation** | `openspec validate poe2-companion-live-uat-defect-remediation --strict --json` | **Valid**, 0 issues |

---

## 6. Real Client.txt Retest Results

- **Log File**: Real local `Client.txt` (Size: 2,149,271 bytes, 19,791 lines).
- **Read-Only Hash Before**: `64819e11b1fb3831336db9f7c70b9dfe8a0da74d803c2c84429a88ff6c2557ef`
- **Read-Only Hash After**:  `64819e11b1fb3831336db9f7c70b9dfe8a0da74d803c2c84429a88ff6c2557ef`
- **Integrity Match**: `True` (0 bytes modified, strictly read-only).
- **Multi-Batch Streaming Evidence**:
  - 20 sequential batches polled with `max_lines=1000`.
  - Total recognized events extracted: 66 (previously 2).
  - Final read offset: `2149271` bytes (100% of file consumed without skipping).
- **PoE2 Level-Up Parsing Evidence**:
  - Total level-up events extracted: 49 (previously 0).
  - Observed format with class token verified: e.g. `Level 2..50`, `Class: Monk`.
- **Privacy Filter Verification**:
  - 0 chat messages leaked across all 19,791 lines (100% privacy compliance).

---

## 7. Live Provenance Retest (UNKNOWN != 0)

- **Scenario**: Audit candidate boots requiring 52 Strength against character with default unobserved attributes.
- **Previous Broken Output**:
  ```text
  Active conflicts: 1
    * [ItemSlot.BOOTS] Unmet Strength requirement: Item requires 52 Str, but observed character has 0 Str.
  ```
- **Observed Remediated Output**:
  ```text
  Gear Status for Character 'test_cli_hero':
    Audited slots: 1
    - boots: Storm Tread [SINGLE_SOURCE]
  ```
- **JSON Output**: `"conflicts": []`
- **Verdict**: PASS. No factual zero Strength claim, no false unmet requirement conflict, uncertainty properly preserved.

---

## 8. Code Review Findings
- Clean type-hinted helper `_extract_verified_attribute()` supporting `ProvenancedField` and `OperandEvidence`.
- Binary stream tailing avoids Windows CRLF character offset translation issues.
- Strict privacy filter executes before regex pattern evaluation.
- No new external dependencies introduced.

---

## 9. Deviations & Blockers
- **Deviations**: None.
- **Remaining Blockers**: None.
