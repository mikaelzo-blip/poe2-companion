# Design: PoE2 Companion Live UAT Defect Remediation

## Context

See `proposal.md` for background and defect findings from `docs/audits/LIVE_UAT_V01.md`.
The live operational acceptance test identified three distinct production defects:
1. `P0 — UNKNOWN_COERCED_TO_ZERO`: Gear mechanical conflict evaluation coerces unobserved character attributes to `0`, generating false unmet requirement warnings.
2. `P1 — CLIENT_LOG_TAILER_CHUNK_TRUNCATION`: Tailer advances read offset to EOF while processing only `lines[:max_lines]`, permanently discarding lines 1,001+ in large backlogs.
3. `P1 — POE2_LEVEL_UP_CLASS_TOKEN_MISMATCH`: Level-up regex fails to match PoE2 lines with class tokens (e.g. `: BOMSHAK (Mercenary) is now level 11`).

## Goals / Non-Goals

**Goals:**
- Eliminate default-zero attribute coercion in `companion/gear/conflicts.py` and enforce that `UNKNOWN != 0` and `UNPROVENANCED VALUE != VERIFIED FACT`.
- Reject plain numeric values (`int`, `float`) without explicit provenance metadata from acting as verified facts in conflict evaluation.
- Wire character state attribute retrieval into `handle_gear_status` in `companion/cli.py` while respecting provenance states.
- Migrate legacy unit test fixtures passing raw integers to supply explicit verified evidence wrappers.
- Define and implement a robust binary-mode byte-offset decoding contract in `ClientLogTailer.poll()` that guarantees multi-batch backlog continuity, UTF-8 replacement decoding, and resilience against malformed bytes.
- Update `_LEVEL_UP_RE` to parse PoE2 level-up lines with optional class tokens while maintaining full backward compatibility with legacy formats.
- Add focused regression tests using sanitized, minimal log fixtures.
- Define a sanitization policy for `docs/audits/LIVE_UAT_V01.md` and a planned `.gitignore` task for `runtime/`.

**Non-Goals:**
- Continuous background daemon / runtime loop (explicitly out of scope per user direction; to be planned after these defect fixes pass live re-test).
- PoE2 zone generation event re-mapping (`Generating level ... area ...` vs `Entered area ...`).
- Committing real `Client.txt` files or private chat messages into the repository.
- Introducing a new generic provenance framework (use existing `ProvenancedField` and `OperandEvidence`).
- Modifying `.gitignore` during the planning phase.

## Decisions

### Decision 1: Strict Provenance Extraction for Mechanical Conflict Evaluation & Rejection of Raw Integers

**Choice**: Introduce helper logic in `companion/gear/conflicts.py` to extract verified attribute values:
- Accept `character_attributes: Mapping[str, Any] | None`.
- For each attribute key (`str`, `dex`, `int`), inspect the provided value:
  - If missing or `None`: evaluate as `UNKNOWN`.
  - If a plain numeric value (`int`, `float`) without provenance wrapper: evaluate as `UNKNOWN` / `INSUFFICIENT_EVIDENCE`. Plain numeric values do NOT establish provenance and must never silently become `VERIFIED`.
  - If a `ProvenancedField`: verify all approved evidence criteria:
    - value is present (`field.value is not None`)
    - supported source (e.g., `"character_sheet"`, `"client_log"`, `"official_api"`, `"test"`)
    - fresh (`not field.is_stale`)
    - `field.verification_state == VerificationState.VERIFIED`
    If any check fails, evaluate as `UNKNOWN`.
  - If an `OperandEvidence`: verify `op.is_usable` and `op.verification_state == VerificationState.VERIFIED`. If failed, evaluate as `UNKNOWN`.
- Core Provenance Invariant:
  - Missing attribute $\rightarrow$ `UNKNOWN`.
  - Plain unprovenanced numeric attribute $\rightarrow$ `UNKNOWN` / insufficient evidence.
  - Factual unmet requirement conflict emitted **ONLY** when:
    $$\text{VERIFIED character attribute value} < \text{VERIFIED item requirement}$$
  - When character attribute is `UNKNOWN`, suppress factual unmet requirement conflicts (`UNMET_ATTRIBUTE`). Do NOT substitute `0`.
- Update `handle_gear_status` in `companion/cli.py` to load `char_state = CharacterStateStore(args.runtime).load_character(char_id)` and pass `char_state.attributes` into `detect_mechanic_conflicts(item, character_attributes=char_state.attributes)`.

**Alternatives Considered**:
- *Treat raw int as verified*: Rejected because an integer alone carries no provenance metadata, violating core project provenance rules.
- *Emit an INSUFFICIENT_EVIDENCE warning*: Rejected because uninspected characters in early progression would generate noisy warnings on every slot.

### Decision 2: Legacy Test Fixture Migration Strategy

Because raw integers are rejected in production conflict evaluation:
- Existing tests in `tests/gear/test_evaluator_and_conflicts.py` (e.g. line 136 `char_stats = {"str": 60, "dex": 20, "int": 10}`), `tests/test_m8_integration.py` (line 133), and `tests/test_m9_integration.py` (line 68) must be migrated.
- Migration approach:
  Wrap test attributes in `ProvenancedField[int].create(value, source="test", verification_state=VerificationState.VERIFIED)`.
- Add dedicated negative tests verifying that passing raw integers (e.g. `{"str": 10}`) evaluates to `UNKNOWN` / insufficient evidence and emits zero factual unmet attribute conflicts.

### Decision 3: Audit of All Default-Zero Sites in Gear Evaluation

All occurrences of `.get(..., 0)` or default-zero patterns across `companion/gear/` were inspected:
1. `companion/gear/conflicts.py:40, 53, 66`:
   `attrs.get("str", 0)`, `attrs.get("dex", 0)`, `attrs.get("int", 0)`
   → **Identified as the root cause defect sites**. Replaced with provenance-preserving helper.
2. `companion/gear/evaluator.py:50, 57, 62, 67, 72, 77`:
   `values[mod.key] = values.get(mod.key, 0.0) + float(...)`
   → Accumulates additive numerical modifier magnitudes from parsed tooltip lines (e.g. `+20% Fire Resistance`). Absence of a modifier on an item means 0 added resistance from that specific item. This is correct accumulator logic, not character state coercion.
3. `companion/gear/evaluator.py:92`:
   `actual_val = mod_values.get(req_key, 0.0)`
   → Compares item modifier values against target build modifier thresholds. Correct for item stats.
4. `companion/gear/advisor.py:58, 120`:
   `mod_values.get(req_key, 0.0)` and `breakdown = {k: cand_mods.get(k, 0.0) - eq_mods.get(k, 0.0)...}`
   → Compares candidate item affix rolls against equipped item rolls. Correct for delta calculation.
5. `companion/sources/reporter.py:102-104`:
   Count lookups on summary dictionaries.

Conclusion: Only `companion/gear/conflicts.py` required remediation.

### Decision 4: Line-Bounded Incremental Reading & Binary Client.txt Decoding Contract

**Choice**: Refactor `ClientLogTailer.poll(max_lines=1000)` to use binary-safe line reading with exact consumed byte offset tracking:
- **Mode & Offsets**: Open `self.log_path` in `"rb"` mode. All stream offsets are byte offsets only.
- **Reading Loop**: Seek to byte offset `self._offset`. Read records line-by-line using `f.readline()`.
- **Line Boundary Rule**:
  - Only complete records terminating in `b"\n"` advance the persisted byte offset.
  - If a read line does not end with `b"\n"` (incomplete trailing write in-flight by the game): break immediately without advancing `last_consumed_offset` past the start of this incomplete line.
- **Binary Decoding Contract**:
  - Each complete byte line is decoded using UTF-8 with character replacement: `line_bytes.decode("utf-8", errors="replace")`.
  - Non-ASCII characters (e.g., character names with accents or special characters) decode properly.
  - Malformed or undecodable byte sequences: replaced safely with Unicode replacement character `\ufffd` without raising `UnicodeDecodeError`.
  - Malformed lines are evaluated against `parse_log_line()`. If unrecognized or malformed, they return `None` safely.
  - Malformed lines cannot corrupt byte offset tracking or cause subsequent valid events to disappear.
- **Batching & Offset Advance**:
  - After each complete line is processed, update `last_consumed_offset = f.tell()`.
  - Increment `consumed_count`. When `consumed_count >= max_lines`: break.
  - Set `self._offset = last_consumed_offset`.
- **Truncation / Rotation Handling**:
  - If `stat().st_size < self._offset`, reset `self._offset = 0`.

**Alternatives Considered**:
- *Chunk reading in text mode (`f.read()`)*: Rejected because `f.tell()` in text mode on Windows or with multibyte UTF-8 characters is not a reliable character index and causes chunk truncation bugs.
- *Strict UTF-8 decode without replacement*: Rejected because a single corrupted byte in `Client.txt` would crash the tailer and block all future log processing.

### Decision 5: Dual-Format PoE2 Level-Up Regex

**Choice**: Update `_LEVEL_UP_RE` in `companion/sensing/client_log.py` to:
```python
_LEVEL_UP_RE = re.compile(
    r':\s+(?P<char>[a-zA-Z0-9_\u00C0-\u017F-]+)(?:\s+\((?P<class>[a-zA-Z0-9_\s-]+)\))?\s+is now level\s+(?P<level>\d+)'
)
```
- The non-capturing group `(?:\s+\((?P<class>[a-zA-Z0-9_\s-]+)\))?` makes the parenthetical class token optional.
- Matches both:
  - PoE2 real log: `: BOMSHAK (Mercenary) is now level 11`
  - Legacy format: `: Mercenary_Exile is now level 52`
- When the class token is present, populate `payload["character_class"] = m.group("class")`.
- When absent, omit `payload["character_class"]` (preserving existing payload structure).
- Does not invent class mappings; records the literal observed class token.

### Decision 6: LIVE_UAT Sanitization and Runtime Repository Hygiene

**LIVE_UAT Sanitization Policy**:
Before `docs/audits/LIVE_UAT_V01.md` is committed:
- Sanitize machine-specific local paths (e.g. replace `E:\SteamLibrary\steamapps\common\...` with `<PoE2_Install_Dir>/logs/Client.txt`).
- Sanitize personal/real character identifiers where not strictly required as technical evidence (e.g. replace private character names with sanitized test names while retaining evidence of class tokens).
- Verify 0 private chat lines, 0 credentials, 0 sensitive tokens.

**Runtime Ignore Policy**:
- Inspection of current `.gitignore` revealed:
  `runtime/characters/`, `runtime/backups/`, `runtime/*.lock`, `runtime/*.json`.
- Files like `runtime/journey_history.jsonl` were not covered, leaving `runtime/` untracked in `git status`.
- Add a planned implementation task in `tasks.md` to update `.gitignore` so that `runtime/` is comprehensively ignored while preserving any intentional tracked templates.
- **Guardrail**: Do not edit `.gitignore` during the planning phase.

## Risks / Trade-offs

- **[Risk]**: Binary readline performance on large files.
  - **Mitigation**: Python `BufferedReader.readline()` is implemented in C and processes tens of thousands of lines per second. Bounding by `max_lines` ensures each poll executes in milliseconds.
- **[Risk]**: Migrating legacy unit tests from raw ints could touch multiple test files.
  - **Mitigation**: Scoped only to test files directly testing `detect_mechanic_conflicts` (`test_evaluator_and_conflicts.py`, `test_m8_integration.py`, `test_m9_integration.py`). Helper constructors keep test code concise and explicit.

## Migration Plan

- Direct backward-compatible update to `companion/gear/conflicts.py`, `companion/sensing/client_log.py`, and `companion/cli.py`.
- Test suite migration to wrap legacy test attributes in `ProvenancedField`.
- Rollback: Revert the commit if needed.

## Open Questions

None. All defect causes, required behaviors, and architectural boundaries are fully specified.
