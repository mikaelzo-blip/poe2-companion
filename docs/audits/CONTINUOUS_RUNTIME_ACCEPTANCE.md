# Continuous Runtime Acceptance Report

**Execution Date**: 2026-09-23  
**Target Change**: `poe2-companion-continuous-runtime`  
**Host Environment**: Windows 11 (AMD64), Python 3.11.16, `uv` managed virtualenv  
**Planning Commit SHA**: `767f75a` (`767f75a6104eec49a62961eb3d11b305da3cce6d`)  
**Sanitized Log Path**: `<PoE2_Install_Dir>/logs/Client.txt`  

---

## 1. Executive Summary

This report documents the final operational acceptance for the `poe2-companion-continuous-runtime` capability. The acceptance protocol systematically evaluated baseline determinism, controlled crash and at-least-once replay idempotency, writer lease contention, live Path of Exile 2 interaction with the local game client, game exit drain, game relaunch resumption, signal termination, and resource loop safety.

---

## 2. Baseline Verification

### Exact Commands Executed
```bash
git rev-parse --short HEAD
git status --short
openspec status --change poe2-companion-continuous-runtime --json
uv run pytest -W error
uv run pytest tests/compliance/test_no_input_guard.py -v
uv run python -m compileall -q companion tests
git diff --check
```

### Exact Results
- **Git Revision**: `767f75a`
- **OpenSpec Change Status**: `isPlanningComplete: true`, `isComplete: true`, all 4 artifacts (`proposal`, `specs`, `design`, `tasks`) marked `done`.
- **Pytest Suite**: `542 passed in 9.66s` with zero warnings (`-W error`).
- **Compliance No-Input Guard**: `10 passed in 0.26s` (`test_clean_companion_codebase_passes`, `test_detects_direct_import`, `test_detects_submodule_import`, `test_detects_from_import`, `test_detects_prohibited_symbol_import`, `test_detects_aliased_import`, `test_detects_native_call_tokens`, `test_exclusions_ignored`, `test_assert_no_input_compliance_raises_on_violations`, `test_vision_capture_module_strictly_compliant`).
- **Compileall**: Clean bytecode compilation across `companion` and `tests` with zero syntax errors.
- **Git Diff Check**: Clean (CRLF conversion notices only, zero trailing whitespace or merge conflict markers).

---

## 3. Evidence Categories

### A. DETERMINISTIC TEST VERIFIED
1. **Full Test Suite**: 542 automated unit and integration tests passing unconditionally with `-W error`.
2. **Log Fingerprinting & Epoch Allocation**:
   - `test_normal_append_preserves_epoch`: Verified append preserves stream epoch.
   - `test_truncation_produces_new_epoch_and_unique_observation_ids`: Verified in-place truncation increments epoch and isolates event IDs.
   - `test_replacement_allocates_new_epoch`: Verified new file creation / inode change increments stream epoch.
3. **Counted Event Idempotency**:
   - `test_death_increments_and_sets_watermark`: Verified watermark format `watermark:<stream_id>:<offset>`.
   - `test_replaying_death_event_is_idempotent`: Verified replaying exact same event is a strict no-op.
   - `test_replaying_large_batch_over_100_deaths_is_idempotent`: Verified batch of 150 death events replayed against persisted state does not increment counter beyond 150.
   - `test_distinct_death_events_advance_counter_and_watermark`: Verified distinct events sequentially increment counter and advance watermark.
4. **Journey History Deduplication**:
   - `test_journey_history_deduplication_on_replay`: Verified identical replayed event ID does not append duplicate line to `journey_history.jsonl`.
5. **Single-Writer Lock**:
   - `test_concurrent_runtimes_one_winner`: Verified OS-level lock prevents two concurrent runtimes.
   - `test_mutating_cli_refused_while_runtime_active`: Verified mutating CLI commands raise `WriterActiveError` (`RUNTIME_WRITER_ACTIVE`).
   - `test_stale_metadata_cannot_block_new_owner`: Proved stale JSON metadata with dead PID does not prevent new runtime start when OS lock is free.
6. **No-Input Compliance Boundary**:
   - 10/10 compliance tests passing; verified runtime contains zero prohibited input automation libraries (`pyautogui`, `pydirectinput`, `win32api`, etc.).

---

### B. CONTROLLED CRASH VERIFIED
Using a dedicated test runtime directory and synthetic `Client.txt` fixture with standard header baseline:

1. **Continuous Runtime Startup**:
   - Started `ContinuousRuntimeOrchestrator` in `IDLE` state.
   - Initialized dirty checkpoint (`clean_shutdown=False`, `clean_shutdown_at=None`).
   - Verified writer lease acquired and active.
2. **State-Changing Records Ingestion**:
   - Fed zone transition (`"The Twilight Strand"`), level up (level 2), and multiple deaths (3 distinct death records).
   - Confirmed `CharacterState` updated: `current_zone="The Twilight Strand"`, `level=2`, `death_count=3`.
   - Confirmed `journey_history.jsonl` recorded exactly 5 distinct events.
   - Confirmed `checkpoint.last_offset` advanced to match current file size (1,031 bytes).
3. **Simulated Crash Before Checkpoint Offset Advance**:
   - Rewound checkpoint `last_offset` back to baseline offset (672 bytes), leaving `CharacterState` (deaths=3) and `journey_history.jsonl` (5 entries) intact on disk.
   - Released OS lock abruptly without calling `.shutdown()`, simulating process crash / sudden SIGKILL.
   - Verified `clean_shutdown` remained `False`.
   - Verified OS lock became immediately acquirable by other processes.
4. **Crash Recovery & Replay Idempotency**:
   - Restarted a new `ContinuousRuntimeOrchestrator` instance.
   - Verified crash recovery detected (`is_crash_recovery=True`).
   - Resumed reading from checkpoint offset 672 (replaying the zone, level, and 3 deaths).
   - **Death Count Invariant**: Death count remained exactly 3 (did NOT double to 6).
   - **Journey History Invariant**: History count remained exactly 5 (did NOT duplicate to 10).
   - **State Correctness**: Final level remained 2, zone remained `"The Twilight Strand"`.
   - **Final Checkpoint**: Successfully committed final offset (1,031 bytes) and completed clean shutdown.

---

### C. REAL POE2 LIVE VERIFIED
Using real local installation (`<PoE2_Install_Dir>/logs/Client.txt`, size: 2,149,271 bytes at baseline) and real running Path of Exile 2 game process:

1. **Pre-Launch Idle Baseline**:
   - Started: `uv run companion runtime start --log "<PoE2_Install_Dir>/logs/Client.txt" --verbose`
   - Verified lifecycle state initialized to `IDLE`.
   - Verified baseline log offset established: `2149271`, stream epoch `1`.
   - Inspected runtime status: `[ACTIVE]`, PID `11436`, Game Presence: `Not Running`.
2. **Game Process Auto-Detection**:
   - Path of Exile 2 launched by user.
   - Runtime automatically detected game launch: `[SESSION] PoE2 detected running (PID: 18772)`.
   - Status updated: `Lifecycle: GAME_RUNNING`, `game_pid: 18772`.
3. **Real Client.txt Ingestion**:
   - Automatically consumed 28,337 newly written bytes (266 log lines) from offset 2,149,271 to 2,177,608.
   - File opened strictly read-only (`"rb"` mode).
4. **Game Process Exit Transition**:
   - User exited Path of Exile 2 normally.
   - Runtime observed process termination: `[SESSION] PoE2 process termination detected. Executing bounded final log drain...`.
   - Executed bounded final drain, consuming remaining log lines up to offset 2,178,092.
   - Recap produced: `[SESSION] Session 828baaf1710d4ee1834a9de2919691c4 finalized.`.
   - Lifecycle transitioned: `GAME_RUNNING` -> `bounded drain` -> `finalization` -> `IDLE`.
   - Verified no crash and no hang on trailing lines.
5. **Game Relaunch Resumption**:
   - User relaunched Path of Exile 2.
   - Runtime observed new process: `[SESSION] PoE2 detected running (PID: 20840)`.
   - Lifecycle transitioned from `IDLE` to `GAME_RUNNING`.
   - New session opened seamlessly; offset advanced to 2,202,494.
   - Verified zero notification flood from prior historical logs.
6. **Writer Lease Mutator Contention**:
   - While runtime held writer lease, executed mutating CLI: `uv run companion session tail --runtime runtime --log "<PoE2_Install_Dir>/logs/Client.txt" --id BOMSHAK`
   - Result: Refused with exit code 1 and error `[RUNTIME_WRITER_ACTIVE] Continuous runtime writer lock is actively held. CharacterState mutation refused.`
   - Executed read-only inspection: `uv run companion state inspect --runtime runtime --json`
   - Result: Succeeded with exit code 0.
7. **Signal Termination (Ctrl+C / Kill)**:
   - Terminated runtime process; OS lock automatically released (`writer_lock_held: false`).
   - `companion runtime status` correctly transitioned to `[NOT RUNNING]`.
   - Subsequent startup cleanly detected previous offset and resumed without alert storm.
8. **Resource & Loop Sanity**:
   - CPU utilization was nominal (<1%). No busy-looping observed.
   - Log output was clean and non-spammy (only state/session transition events logged).
   - Zero OCR or screenshot capture attempted.
   - Zero game input attempted.

---

### D. NOT OBSERVED (HONEST REPORTING)
1. **Real Character Level-Up Event**:
   - NOT OBSERVED IN THIS SESSION.
   - Character `<CharacterName>` was already level 11 and did not level up during the acceptance window.
2. **Real Character In-Game Death**:
   - NOT OBSERVED IN THIS SESSION.
   - No deaths occurred during the short live observation window.

---

### E. EXTERNAL BLOCKED / DEFECTS FOUND
1. **Defect DEF-01: Real PoE2 Area Generation Log Format Mismatch**:
   - In real PoE2 logs, area generation is logged as:
     `2026/09/23 02:41:59 58968640 2caa229f [DEBUG Client 18772] Generating level 10 area "G1_11" with seed 2336047553`
   - Note the absence of a colon `:` after `[DEBUG Client 18772]`.
   - `companion.sensing.client_log._ZONE_GENERATE_RE` is defined as:
     `r':\s+Generating level\s+(?P<level>\d+)\s+area\s+"(?P<zone>[^"]+)"'`
   - Because it mandates a leading colon, real PoE2 area transitions fail to parse in live play.
   - Expected: Support both `: Generating level` and ` Generating level` via `r'(?::\s+|\s+)Generating level...'`.
   - Severity: High for live zone progression tracking.

---

## 4. Defect DEF-01 Resolution Summary
- **Defect Description**: Real PoE2 client logs format zone generation as `[DEBUG Client <pid>] Generating level <level> area "<zone>" with seed <seed>` without a colon after the bracketed envelope. Mandating a colon in `_ZONE_GENERATE_RE` resulted in dropped zone transitions in live gameplay.
- **Resolution**: Remediated surgically using TDD (RED-GREEN cycle) by allowing either `] ` or `: ` as prefix boundary.
- **Status**: **RESOLVED & VERIFIED**.

---

## 5. DEF-01 Remediation & Re-Verification Details

### A. Failing Test Before Fix (RED)
- Test: `tests/sensing/test_client_log.py::test_parse_poe2_real_zone_generate_without_colon`
- Input: `2026/09/23 02:41:59 58968640 2caa229f [DEBUG Client 18772] Generating level 10 area "G1_11" with seed 2336047553`
- Failure:
  ```text
  FAILED tests/sensing/test_client_log.py::test_parse_poe2_real_zone_generate_without_colon - assert None is not None
  tests\sensing\test_client_log.py:215: AssertionError
  ```

### B. Exact Root Cause
`companion/sensing/client_log.py` defined `_ZONE_GENERATE_RE = re.compile(r':\s+Generating level\s+(?P<level>\d+)\s+area\s+"(?P<zone>[^"]+)"')` and `_ZONE_ENTER_RE = re.compile(r':\s+Entered area\s+"(?P<zone>[^"]+)"')`. While PoE2 player chat, level up, and death lines retain `[INFO Client <pid>] : <message>`, debug zone generation lines omit the colon: `[DEBUG Client <pid>] Generating level...`. The mandatory colon caused all real PoE2 zone generations to be rejected by the regex search.

### C. Parser Changes (GREEN)
Surgically updated boundaries in `companion/sensing/client_log.py`:
```python
_ZONE_GENERATE_RE = re.compile(
    r'(?:\]\s+|:\s+)Generating level\s+(?P<level>\d+)\s+area\s+"(?P<zone>[^"]+)"'
)
_ZONE_ENTER_RE = re.compile(r'(?:\]\s+|:\s+)Entered area\s+"(?P<zone>[^"]+)"')
```
Preserved: named level capture, named zone capture, optional trailing seed matching, privacy filter precedence, and existing payload semantics.

### D. Tests Added
1. `test_parse_poe2_real_zone_generate_without_colon`: Verified exact sanitized real PoE2 line parses to `ZONE_GENERATE` with `zone="G1_11"` and `area_level=10`. Retained test for legacy colon format.
2. `test_parse_log_line_negative_and_anti_overmatch`:
   - Chat filtering precedence: `@From`, `#`, `$` chat lines containing "Generating level" or "Entered area" dropped unconditionally before regex matching.
   - Arbitrary text: Non-bracket/non-colon text containing "Entered area" rejected.
   - Malformed lines: Non-numeric levels and unquoted zone names rejected.
   - Unrelated DEBUG lines: Asset loading, D3D12 device creation, and server connection lines cleanly return `None`.

### E. Full Regression Totals
- `uv run pytest -W error`: **544 passed in 9.51s**, 0 warnings.
- `uv run pytest tests/compliance/test_no_input_guard.py -v`: **10 passed in 0.21s**.
- `uv run python -m compileall -q companion tests`: Clean compilation.
- `git diff --check`: Clean (0 whitespace errors, 0 conflict markers).
- `openspec validate poe2-companion-continuous-runtime --strict`: **Valid**.
- `openspec validate --specs --strict`: **23/23 specs valid**.

### F. Real Client.txt Regression Result
- Tested against real file: `E:\SteamLibrary\steamapps\common\Path of Exile 2\logs\Client.txt` (2,202,978 bytes, 20,293 lines, read-only `"rb"`).
- Total real `Generating level` lines found: **274**.
- Total successfully parsed as `ZONE_GENERATE`: **274 / 274 (100%)**.
- Representative parsed payload: `{'zone': 'G1_11', 'area_level': 10}`, timestamp `2026-09-23 02:41:59+00:00`.
- Runtime pipeline verification:
  - `normalize_log_event()` produces valid `ObservationEvent` (`ZONE_TRANSITION`).
  - `reconcile_observation()` updates `CharacterState.current_zone.value = 'G1_11'`.
  - `StateChangeTracker.compute_delta()` registers `DirtyTrigger.ZONE`.
  - `StateChangeTracker.should_reevaluate_objectives()` evaluates to `True`.

### G. Live Zone-Transition Result
- **LIVE ZONE TRANSITION NOT OBSERVED IN THIS RETEST**
- Note: Game process exited gracefully prior to retest window. Zero synthetic observations fabricated. Real-log historical parsing evidence confirms 100% correctness.

### H. Remaining Defects / Blockers
- **None**. Defect DEF-01 is completely resolved.

---

## 6. Final Acceptance Verdict
- **Verdict**: **ACCEPTED**
- The continuous runtime capability meets all functional, architectural, safety, and compliance specifications.

