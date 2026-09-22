# Change Proposal: Milestone 9 — Expanded Build Intelligence

## Why

After establishing reliable core state reconciliation, read-only vision sensing, and gear auto-analysis, the companion requires deeper domain advisory to guide the player through survival gating, gear optimization, gameplay troubleshooting, permanent quest milestone tracking, and foundational economy decisions without violating the strict no-input/read-only compliance policy.

## What Changes

1. **Domain Advisory Rules Engine**:
   - `SurvivalRules`: Evaluates elemental resistances (capped at 75%), life pool scaling by act/level, and chaos resistance pacing.
   - `GearRules`: Identifies socket count gaps, missing bench-crafted affixes on rare items with open slots, and under-leveled base types.
   - `TroubleshootingRules`: Diagnoses attribute bottlenecks, mana reservation locks leaving inadequate casting mana pool, and missing ailment flask mitigations.
2. **Minimal Story Progression Guidance**:
   - Tracks act quest checkpoints providing permanent passive skill points and spirit capacity.
   - Alerts player when advancing zones without having claimed critical permanent story rewards.
3. **Minimal Economy & Upgrade Prioritization**:
   - Provides upgrade investment ROI guidance (e.g. weapon base upgrade for attack builds vs resist jewelry for survivability).
   - Flags high-value vendor recipes and progression-appropriate currency exchange pacing.
4. **CLI Integration**:
   - Adds `companion intelligence audit`, `companion intelligence story`, and `companion intelligence economy` subcommands.
5. **Quality & Compliance**:
   - 100% passive, zero-game-input, zero-memory-mutation operation verified by test suites.
