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
