# Design

## Context

See `proposal.md` for motivation and background. Milestone 7 provides the visual sensing pipeline. Per Blueprint Sections 13, 14, 15, and 16, visual sensing must operate under strict cost budgets, explicit privacy disclosures, and semantic verification states rather than uncalibrated LLM confidence scores.

## Goals / Non-Goals

**Goals:**
- Provide a modular vision architecture separating budget tracking, privacy redaction, screen classification, and text/OCR parsing.
- Support deterministic parsing of the PoE2 character panel for defensive stats and resistances.
- Enforce semantic verification states: multi-capture stability yields `VERIFIED`, single capture yields `SINGLE_SOURCE`, discrepancy yields `CONFLICTING`.
- Enforce strict hourly call limits and inter-capture cooldowns.
- Clear disclosure of cloud transmission vs local processing.

**Non-Goals:**
- Direct OS window hooking or keyboard/mouse input simulation.
- Continuous screen scraping during active combat.
- Reconstructing full passive tree geometry from screenshots.

## Decisions

1. **Screen Classification Hierarchy**:
   - Classification inspects landmark tokens: "Character", "Defences", "Resistances", "Armour", "Evasion" -> `CHARACTER_PANEL`.
   - "Requires Level", "Item Level", "Implicit", "Rarity" -> `ITEM_TOOLTIP`.
   - Fall back to `UNKNOWN` when landmarks are absent.

2. **Semantic Verification States**:
   - `VERIFIED`: 2+ consecutive captures within stability interval yielding identical stats and valid ranges.
   - `SINGLE_SOURCE`: 1 capture parsed cleanly.
   - `CONFLICTING`: Discrepancy between consecutive captures or out-of-bounds metrics.

3. **Vision Budget Tracker**:
   - Rolling 60-minute window for `max_calls_per_hour` (default: 120).
   - Cooldown interval between captures (default: 15 seconds).
   - In-memory ring buffer with eviction of timestamps older than 1 hour.

4. **Privacy and Redaction**:
   - Redaction filters strip player account names and masked chat regions before passing text/data to downstream extractors.
   - Explicit string disclosures generated for audit logging.

## Risks / Trade-offs

- [Risk: OCR / LLM text variability in stat names] → Mitigation: Regex parsers support common aliases (e.g. "Fire Resistance", "Fire Res", "+XX% to Fire Resistance").
- [Risk: Excessive API costs if polling loops run unchecked] → Mitigation: Hard ceiling enforced by `VisionBudgetTracker.check_and_consume()`.
