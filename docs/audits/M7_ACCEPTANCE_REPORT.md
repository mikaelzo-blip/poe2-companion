# Milestone 7 Acceptance Report: Read-Only Vision Sensor + Budget + Panel Parser

## Executive Summary
Milestone 7 integrates a passive, read-only visual extraction sensor for Path of Exile 2. It features landmark-based screen classification, character defensive panel parsing, multi-capture semantic corroboration (`VERIFIED` vs `SINGLE_SOURCE` vs `CONFLICTING`), a strict hourly and cooldown budget tracker, local screenshot caching with TTL/LRU eviction, and privacy disclosures with sensitive identity/chat redaction. The subsystem maintains strict no-input compliance and zero game memory mutation.

## Key Deliverables Implemented
1. **Vision Domain Models & Privacy**:
   - `ScreenType` (`CHARACTER_PANEL`, `ITEM_TOOLTIP`, `SKILL_PANEL`, `PASSIVE_SCREEN_TARGETED`, `UNKNOWN`).
   - `CharacterPanelStats` tracking core defenses: life, mana, spirit, armour, evasion rating, and elemental/chaos resistances.
   - `VisionPrivacyConfig` declaring local vs cloud processing modes, with `redact_sensitive_text` sanitizing character/account names and chat overlays.
2. **Vision Budget Tracker**:
   - `VisionBudgetTracker` with rolling 60-minute hourly call limiting (`max_calls_per_hour = 120`) and inter-capture cooldown enforcement (`min_seconds_between_captures = 15.0s`).
3. **Screen Classification & Stat Parsing**:
   - `classify_screen` detecting categorical landmarks with confidence scoring.
   - `parse_character_panel` robustly extracting defensive numeric values via regex pattern matching.
   - `evaluate_verification_state` comparing multi-capture observations into semantic verification states.
4. **Screenshot Artifact Cache**:
   - `ScreenshotCache` supporting TTL-based expiration (`ttl_minutes = 30`) and disk capacity limits (`max_mb = 500`) with LRU eviction.
5. **CLI Subcommands**:
   - `companion vision status`: displays tracker status, hourly budget usage, and privacy mode disclosure.
   - `companion vision parse-panel`: parses text fixture from file or stdin into structured stats and emits observation event to bus.

## Verification & Test Results
- Total Tests: 376 passed cleanly.
- `tests/vision/test_budget_and_privacy.py`: 4 passed.
- `tests/vision/test_classifier_and_parser.py`: 5 passed.
- `tests/vision/test_cache.py`: 3 passed.
- `tests/cli/test_m7_cli.py`: 2 passed.
- `tests/test_m7_integration.py`: passed full end-to-end multi-capture corroboration and observation bus emission.
- Static No-Input Compliance: 9 passed, 0 violations.
- Canonical Specs: 15 passed validation.
