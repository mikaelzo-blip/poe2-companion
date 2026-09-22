# Design

## Context

See `proposal.md` and `specs/gear-analysis/spec.md`. The vision engine in M7 established read-only capture infrastructure, screen classification, and semantic verification states. Milestone 8 introduces gear domain logic, item tooltip parsing, deterministic hashing, staleness tracking, comparison against progression build rules, durability investment advice, and mechanical conflict detection.

## Goals / Non-Goals

**Goals:**
- Detect stable tooltips using multi-capture verification (2 matching captures).
- Parse item rarity, name, base type, attribute requirements, level requirement, implicit mods, explicit mods, and runes/sockets from tooltip text.
- Compute canonical, deterministic SHA-256 item hashes for persistent slot identity.
- Manage equipment slot audit states with TTL-based expiration.
- Compare equipped gear against target build requirements for the active character progression stage.
- Generate actionable investment advice for upcoming milestones and candidate upgrades.
- Detect observable mechanic conflicts (e.g. unmet attribute requirements, wrong weapon types).
- Provide CLI subcommands: `companion gear audit`, `companion gear compare`, and `companion gear status`.

**Non-Goals:**
- No automated mouse control, screen clicking, or key emulation.
- No direct PoE2 process memory reading or network packet inspection.
- No real-time trade economy pricing scraping.

## Decisions

### Decision 1: Dual-Capture Tooltip Stability Gate
- **Choice**: Require two consecutive matching captures within a short window (e.g., 5 seconds) to declare a tooltip `VERIFIED`.
- **Rationale**: Hovering over items often captures partial fades, cursor occlusion, or transit motion. Requiring two matching captures eliminates noise without player inconvenience.
- **Alternatives Considered**: Single capture (prone to motion blur and partial render), optical flow tracking (unnecessary computational overhead).

### Decision 2: Canonical Item Normalization and Hashing
- **Choice**: Normalize item text (lowercase, trimmed whitespace, sorted explicit mods) and compute a SHA-256 hex digest (`item_hash`).
- **Rationale**: Allows rapid identity comparisons, duplicate detection, and inventory change tracking without storing giant image blobs.

### Decision 3: Slot Isolation in Gear Audit
- **Choice**: Each equipment slot (helm, chest, gloves, boots, main hand, off hand, amulet, rings, belt, swap weapons) maintains its own timestamp, item hash, and verification state.
- **Rationale**: An unverified boots slot must never invalidate an already verified helmet, and verifying one slot never implies coverage of others.

### Decision 4: Rule-Driven Conflict and Durability Evaluator
- **Choice**: Evaluate observable conflicts using character state attributes and target build rules.
- **Rationale**: Ensures deterministic, testable warnings without hallucinated recommendations.

## Risks / Trade-offs

- **[Risk]**: Tooltip text parsing variations due to OCR anomalies.
  - **Mitigation**: Employ robust, flexible regex patterns with case-insensitivity and whitespace normalization.
- **[Risk]**: Player forgets to re-audit gear after swapping equipment.
  - **Mitigation**: Implement configurable TTL (e.g., 60 minutes) that flags gear state as `STALE` and suggests re-audit.
- **[Risk]**: Accidental violation of no-input guardrails.
  - **Mitigation**: Pure functional text-based parsers and CLI commands; static compliance tests enforce zero input/control imports.
