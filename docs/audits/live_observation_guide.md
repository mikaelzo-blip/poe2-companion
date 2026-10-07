# Live Gameplay Development Observation Acceptance Protocol

This document establishes the observation acceptance protocol for the Path of Exile 2 Development Observation Mode (`--observe-dev`, `--observe-screens`). Optional long-duration endurance/stability testing is a separate activity.

## 1. Acceptance Scope & Duration

- **Development-observation acceptance**: At least 30 minutes of continuous real gameplay observation in **one** session. Never add shorter sessions together.
- **Optional endurance/stability soak**: Suggested 60–120 continuous minutes for deeper performance and long-duration stability analysis; not required for every development-observation acceptance.
- **Purpose**: Collect reliable real development evidence while checking non-blocking queue behavior, bounded storage, privacy, and shutdown reconciliation. Duration alone never implies acceptance.
- **Environment**: Windows 11 host running PoE2 client and Continuous Companion Runtime.
- **Gameplay coverage**: No minimum number of zones, deaths, level-ups, genuine selected-objective transitions, or notifications. Mark naturally absent events `NOT OBSERVED` without failing observer acceptance; development conclusions dependent on those events remain `NOT ENOUGH EVIDENCE`.

## 2. Pre-Session Checklist

1. **Verify Git Isolation**:
   Confirm that `.gitignore` prevents `runtime/observations/` from being tracked.
   ```bash
   git status
   ```
2. **Start Companion in Observation Mode**:
   ```bash
   companion runtime start --observe-dev --observe-screens --observe-display 1 --verbose
   ```
3. **Verify Session Initialization**:
   In another terminal:
   ```bash
   companion observe status
   ```
   Confirm that `status: OPEN`, `persisted_event_count: 0`, and `dropped_event_count: 0`.

## 3. Active Session Procedures

### Manual Markers
During gameplay, when notable game events or potential bugs occur (e.g. boss phase transitions, unhandled notifications, frame drops), log manual markers:
```bash
companion observe mark "Boss phase 2 arena transition occurred"
companion observe mark "Expected quest completion notification did not show"
```

### Telemetry & Queue Monitoring
Periodically inspect runtime queue health:
```bash
companion observe status --json
```
Verify:
- `queue_depth` remains low (< 50 items during steady state).
- `dropped_event_count` remains 0 under normal load.
- If queue depth temporarily spikes during heavy area transitions, verify priority shedding drops LOW events before MEDIUM or HIGH.

### Real-Time Live Review & Interruption Verification Protocol
Executed WHILE GAME IS STILL RUNNING:
1. Observer evidence sequence advances monotonically.
2. Local incremental reader advances and can temporarily lag safely.
3. Review batch result (`review_batches/<batch_id>.json`) exists before `hermes_review_cursor.json` advances.
4. Hermes reviews at least one batch while game is running.
5. Review cursor advances only after durable review output/accounting.
6. User creates a marker via atomic inbox (`companion observe mark "<note>"`).
7. Marker appears in persisted observation evidence (`markers.jsonl`).
8. Hermes reviews/correlates that marker while game is running if Hermes is active.
9. Intentionally interrupt Hermes/provider after one completed review batch.
10. Continuous runtime and observer continue running completely unaffected.
11. New evidence accumulates while Hermes is stopped.
12. Local reader continues indexing new evidence.
13. Restart/resume Hermes review.
14. Verify already completed review batch is not re-reviewed unnecessarily (skipped via durable result).
15. Verify no duplicate logical finding or revision upon resume.
16. Pending evidence and offline marker are reviewed (marker prioritized on resume).
17. New evidence after resume produces a new review batch normally.
18. Hermes advances from review cursor.
19. Live status (`companion observe live-status`) accurately reflects `ACTIVE` vs `OFFLINE`, saturation state, batch counts, and both lag values (`reader_lag`, `review_lag`).
Confirming that the 30-minute rule remains solely the dataset acceptance duration threshold and not an analysis delay.

### Hermes AI Review Bridge Acceptance Criteria
During live PoE2 gameplay observation, the following 11 bridge contract invariants must be verified:
1. **Claim-Specific Artifact**: Real Hermes claim artifact is claim-specific (`review_claims/<review_batch_id>.<claim_id>.json`).
2. **Claim Overwrite Immunity**: Another review run or concurrent agent cannot overwrite that claim; both claim artifacts coexist independently on disk.
3. **Non-Overlapping Ranges**: Request ranges remain strictly non-overlapping during live gameplay (e.g. 101–150, 151–200).
4. **Marker Coverage Ownership**: A real marker promotes the scheduling priority of the correct owning request rather than generating duplicate evidence coverage.
5. **No Duplicate Coverage from Priority**: Marker priority updates do not generate duplicate evidence coverage or alter immutable request envelopes.
6. **Out-of-Order Frontier Safety**: A later priority batch can complete first without jumping the contiguous review frontier (`reviewed_ahead_ranges` tracks out-of-order batches).
7. **Contiguous Frontier Catch-Up**: Older batch completion causes the contiguous review frontier to safely catch up across reviewed-ahead ranges.
8. **Zero Double-Review**: No evidence item or sequence is reviewed twice because of overlapping requests.
9. **Observer Decoupling**: Continuous runtime and observer proceed completely unaffected during AI provider interruption, rate-limiting, or task exit.
10. **Resume Skip & Alignment**: Resumed review skips already completed batches and catches up from the preserved cursor.
11. **Strict Write Allowlist Enforcement**: Real Hermes writes zero files outside the approved allowlist (`review_claims/*`, `review_claim_status/*`, `review_responses/*`, `hermes_review_status.json`). Any attempt to touch source code, OpenSpec, tests, or reader state fails the acceptance gate.

## 4. Post-Session Verification & Watermark Reconciliation

1. **Orderly Graceful Termination**:
   Send `SIGINT` (Ctrl+C) to the companion runtime process.
   Observe console logs confirming 9-step shutdown drain.
2. **Manifest Status Verification**:
   ```bash
   companion observe status
   ```
   Confirm:
   - `status: CLOSED` (not `INCOMPLETE` or `FAILED`).
   - `pending_event_count == 0` (queue was fully drained).
   - `persisted_event_count + dropped_event_count == sequence_high_watermark`.
   - `health_state: HEALTHY` and no unresolved worker failure.
   - The saved manifest, JSON summary, and embedded manifest agree on terminal status and end time; check every base and rotated stream for unique contiguous sequence numbers or explained drops and resolved correlation refs.
   - Run a privacy audit without reproducing marker notes, player identifiers, or anomaly samples in the report. Raw artifacts must remain local under `runtime/observations/` and gitignored. If any of these checks fail, the session is not accepted even when it exceeds 30 minutes.
3. **Generate Summary and Review**:
   ```bash
   companion observe summary
   companion observe review --output docs/audits/soak_review_report.md
   ```
4. **Evidence Classification Review**:
   - Confirm unparsed lines are classified under `## 2. Likely Defects` or `## 6. Not Enough Evidence`.
   - Confirm private chat whispers (`@From`, `@To`, `#`, `$`, `%`, `&`, `!`) are absent from all outputs.
   - Any expected events that were not logged must be classified as `NOT OBSERVED`.
