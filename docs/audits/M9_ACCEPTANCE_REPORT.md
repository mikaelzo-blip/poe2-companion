# Milestone 9 Acceptance Report: Expanded Build Intelligence

## Executive Summary
Milestone 9 adds deeper domain intelligence and diagnostic advisories to the Path of Exile 2 Companion. It integrates survival rules evaluating elemental resistance caps and life pool baselines, gear optimization rules detecting open affix bench-craft potential and obsolete base tiers, diagnostic troubleshooting rules for mana starvation and attribute requirement bottlenecks, story quest tracking for permanent passive skill books and spirit capacity shrines, and deterministic economy prioritization guidance. All evaluations are 100% passive, read-only, and strictly compliant with zero-input policies.

## Key Deliverables Implemented
1. **Intelligence Domain Schemas** (`companion/intelligence/schema.py`):
   - `AdvisoryCategory` (`SURVIVAL`, `GEAR`, `TROUBLESHOOTING`, `STORY`, `ECONOMY`).
   - `AdvisorySeverity` (`INFO`, `WARNING`, `CRITICAL`).
   - `AdvisoryItem`, `StoryQuest`, `EconomyPriority`.
2. **Survival Rules Engine** (`companion/intelligence/survival.py`):
   - `evaluate_survival_rules`: evaluates elemental resistances against 75% endgame caps, detects dangerous negative chaos resistance in maps, and alerts on deficient life pools relative to character level.
3. **Gear Rules & Troubleshooting Diagnostics** (`companion/intelligence/gear_rules.py`, `companion/intelligence/troubleshooting.py`):
   - `evaluate_gear_rules`: scans rare items with < 6 affixes for open bench-craft potential, flags gear bases lagging > 20 levels behind character level.
   - `evaluate_troubleshooting_rules`: diagnoses unreserved mana starvation when reservation leaves less than 2x main skill cost, alerts on attribute deficits and tight attribute margins (< 5 points).
4. **Story & Economy Advisors** (`companion/intelligence/story.py`, `companion/intelligence/economy.py`):
   - `evaluate_story_progression` & `get_story_quests`: catalogs permanent passive books and spirit shrines across Acts 1-3+, warning when advancing acts with missed permanent rewards.
   - `evaluate_economy_priorities`: computes an ROI ladder prioritizing capped resistances before weapon DPS scaling, gem links, and endgame uniques.
5. **CLI Integration** (`companion/cli.py`):
   - `companion intelligence audit`: full diagnostic audit across survival, gear, troubleshooting, and story rules.
   - `companion intelligence story`: displays quest checklist with permanent rewards.
   - `companion intelligence economy`: displays upgrade prioritization and ROI guidance.

## Verification & Test Results
- Total Tests: 404 passed cleanly in 2.30s.
- `tests/intelligence/test_survival_rules.py`: 3 passed.
- `tests/intelligence/test_gear_and_troubleshooting.py`: 3 passed.
- `tests/intelligence/test_story_and_economy.py`: 4 passed.
- `tests/cli/test_m9_cli.py`: 3 passed.
- `tests/test_m9_integration.py`: 1 passed (full end-to-end integration across survival, gear, troubleshooting, story, and economy).
- Static No-Input Compliance (`tests/compliance/test_no_input_guard.py`): 9 passed, 0 violations.
- Canonical OpenSpec Specs: 17 passed validation.
