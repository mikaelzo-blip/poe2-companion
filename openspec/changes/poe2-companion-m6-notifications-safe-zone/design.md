# Design

## Context

See `proposal.md` for motivation and background. Milestone 4 provides the `ObjectiveEngine` with categorized priorities, while Milestone 5 provides real-time process monitoring, log tailing, and append-only journey history. Milestone 6 connects these systems to player-facing delivery: delivering urgent alerts while protecting player immersion in combat zones, and providing meaningful session recaps upon conclusion.

## Goals / Non-Goals

**Goals:**
- Provide a decoupled, modular notification delivery architecture with `NotificationSink` abstraction.
- Enforce strict safe-zone awareness: towns and encampments allow deferred notifications to surface; combat zones suppress non-critical alerts.
- Enforce immediate delivery for critical alerts (e.g., survival risks, transition blockers).
- Prevent duplicate alerts using content hashing and a configurable time-based cooldown window.
- Aggregate append-only journey history into deterministic session summaries.

**Non-Goals:**
- Audio synthesis or screen overlay rendering (deferred to future milestones).
- Game state injection or direct memory reading.

## Decisions

1. **Pluggable Notification Sinks**:
   - Define a `NotificationSink` protocol with `send(payload: NotificationPayload) -> bool`.
   - Provide `InMemorySink` (primary for testing and headless runs) and `ConsoleSink` (standard stdout / stderr).
   - Allow chaining multiple sinks.

2. **Safe Zone Classification**:
   - Define `SafeZonePolicy` containing known safe zone keywords and exact area names (e.g., "Clear Fell Encampment", "Town", "Hideout", "Kingsmarch", "Ogham", "Ardura Caravan").
   - Classify all other zones as hostile combat zones.

3. **Priority-Driven Routing**:
   - High severity (`CRITICAL`, or `ObjectivePriority <= 4`): bypasses safe-zone queue and delivers immediately to sinks.
   - Low severity (`WARNING`, `INFO`, or `ObjectivePriority >= 5`): queued if in a combat zone; delivered immediately if in a safe zone.
   - Zone change to safe zone triggers a flush of all queued alerts.

4. **Alert Deduplication**:
   - Key computed from `(category, title, message)` or explicit `dedupe_key`.
   - Maintain in-memory timestamp cache of recent alerts. Discard if elapsed time < cooldown duration (default 120 seconds).

5. **Deterministic Session Recap**:
   - Function `generate_session_recap(entries: list[JourneyHistoryEntry], session_id: str | None) -> SessionRecap`.
   - Pure reduction over journey history events: counts levels gained (min level to max level observed), unique zones visited, and total deaths.

## Risks / Trade-offs

- [Risk: Game area naming varies in client logs] → Mitigation: Case-insensitive substring matching on recognized encampments and town keywords in addition to exact match lists.
- [Risk: Memory leak in long-running cooldown cache] → Mitigation: Prune cooldown cache entries older than 2x the cooldown window during each dispatch.
