# Proposal

## Why

During active Path of Exile 2 gameplay, players need timely, low-friction alerts for critical conditions (such as imminent survival risks or readiness for character weapon swap) without being distracted during intense combat in hostile zones. Furthermore, players need an automatic, objective post-session summary of progress, areas visited, levels gained, and deaths without relying on fallible human recollection or hallucinated model memory.

## What Changes

- Implement a low-latency, non-intrusive notification engine with pluggable notification sinks (in-memory, console, and optional Windows desktop toast).
- Implement an intelligent safe-zone batching policy that classifies game areas into safe zones (towns, hideouts, encampments) versus combat zones.
- Enforce that non-critical advisory and optimization alerts are held in a safe-zone queue during combat and flushed immediately upon returning to safety.
- Allow critical survival and weapon-swap blocker alerts to break through immediately regardless of zone type.
- Implement alert deduplication and configurable cooldown windows to prevent notification spam.
- Implement an automated session recap generator that consumes append-only journey history and outputs a structured post-session milestone report.

## Capabilities

### New Capabilities
- `notification-system`: Alerts players to critical conditions with deduplication, cooldowns, and safe-zone batching.
- `session-recap`: Generates structured, deterministic post-session recaps from normalized journey history.

### Modified Capabilities
(None)

## Impact

- Extends `companion/notifications/` with domain schemas, delivery sinks, safe-zone policies, and queue manager.
- Adds `companion/recap/` with journey history aggregation and recap formatting.
- Adds `companion notify` and `companion session recap` subcommands to `companion/cli.py`.
