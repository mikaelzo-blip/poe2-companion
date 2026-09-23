# Live Play Soak Acceptance Protocol

This document establishes the official soak verification protocol for the Path of Exile 2 Development Observation Mode (`--observe-dev`, `--observe-screens`).

## 1. Acceptance Scope & Duration

- **Session Length**: 60 to 120 minutes continuous live gameplay.
- **Environment**: Windows 11 host running PoE2 client and Continuous Companion Runtime.
- **Objective**: Verify zero production runtime impact, non-blocking queue behavior, bounded storage retention, fail-closed privacy redaction, and clean shutdown watermark reconciliation.

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
3. **Generate Summary and Review**:
   ```bash
   companion observe summary
   companion observe review --output docs/audits/soak_review_report.md
   ```
4. **Evidence Classification Review**:
   - Confirm unparsed lines are classified under `## 2. Likely Defects` or `## 6. Not Enough Evidence`.
   - Confirm private chat whispers (`@From`, `@To`, `#`, `$`, `%`, `&`, `!`) are absent from all outputs.
   - Any expected events that were not logged must be classified as `NOT OBSERVED`.
