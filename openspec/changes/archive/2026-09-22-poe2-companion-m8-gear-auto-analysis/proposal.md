# Proposal

## Why

In Path of Exile 2, evaluating equipped and candidate gear against progression build targets requires careful stat inspection and conflict awareness. To provide actionable guidance without automated inputs or memory tampering, the companion needs a passive gear auto-analysis engine. This evaluates item tooltips, verifies tooltip stability across consecutive captures, parses item stats and requirements, tracks item freshness with TTL, compares equipped gear against target build requirements, provides upgrade investment advice, and detects mechanical conflicts.

## What Changes

- Implement `companion/gear/schema.py` for item models, equipment slots, audit state, comparison results, and mechanic conflicts.
- Implement `companion/gear/tooltip.py` for stable tooltip detection (2-capture corroboration) and text parsing of item rarity, name, base type, stat requirements, implicit/explicit mods, and sockets/runes.
- Implement `companion/gear/hasher.py` generating deterministic item hashes for deduplication and identity tracking.
- Implement `companion/gear/evaluator.py` comparing equipped gear against target build requirements with TTL-based staleness management.
- Implement `companion/gear/advisor.py` producing actionable investment advice and upgrade prioritization for current and next-stage progression.
- Implement `companion/gear/conflicts.py` identifying observable mechanic conflicts such as unmet attribute thresholds or incompatible weapon archetypes.
- Implement `companion/gear/audit.py` orchestrating guided slot-by-slot inventory audits without automated inputs.
- Add CLI commands: `companion gear audit`, `companion gear compare`, and `companion gear status`.

## Capabilities

### New Capabilities
- `gear-analysis`: Evaluates candidate and equipped items via stable tooltip parsing, deterministic item hashing, TTL staleness tracking, current-vs-target build comparison, investment advice, and observable mechanic conflict detection.

### Modified Capabilities
*(None)*

## Impact

- Extends `companion/` with new `companion/gear/` package.
- Integrates with `companion/cli.py` for gear audit and comparison commands.
- Emits observation events via `companion/observations/bus.py` when gear audits complete.
- No impact on external game processes; strictly complies with read-only no-input invariants.
