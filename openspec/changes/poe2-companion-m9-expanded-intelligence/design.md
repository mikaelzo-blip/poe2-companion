# Architectural Design: Milestone 9 — Expanded Build Intelligence

## Architecture Overview

Milestone 9 expands the build intelligence subsystem into functional advisory modules under `companion/intelligence/`:
- `companion/intelligence/survival.py`: Survival rules (resists, life, chaos res pacing, ailment defenses).
- `companion/intelligence/gear_rules.py`: Gear rules (open affixes, craft potential, base tier upgrades, socket capacity).
- `companion/intelligence/troubleshooting.py`: Troubleshooting rules (mana sustain, attribute deficits, flask setups).
- `companion/intelligence/story.py`: Story quest tracking for permanent passives and spirit bonuses.
- `companion/intelligence/economy.py`: Economy & upgrade prioritization rules.
- `companion/intelligence/schema.py`: Shared domain models for advisories, categories, severities, and quest checkpoints.

## Integration with Existing Systems

1. **State & Observations**:
   - Consumes `CharacterState` (level, stats, zone/act).
   - Consumes `CharacterPanelStats` from `companion/vision/schema.py`.
   - Consumes `GearAuditState` from `companion/gear/schema.py`.
2. **Observation Bus**:
   - Publishes advisory evaluation events to `ObservationBus` as `STAT_OBSERVATION` or `OBJECTIVE_UPDATE`.
3. **CLI Interface**:
   - `companion intelligence audit`: evaluates full diagnostic advisory suite.
   - `companion intelligence story`: displays permanent reward quest tracker.
   - `companion intelligence economy`: displays upgrade ROI recommendations.

## Determinism and Safety Invariants
- Functions over autonomous directors: purely deterministic, functional rule evaluators without unpredictable agent behavior.
- Zero game input or memory access: 100% read-only data evaluation.
- Stale and missing data awareness: if gear or defensive stats are unobserved, rules return `UNKNOWN` or informational advisories rather than false failures.
