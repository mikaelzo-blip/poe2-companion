# Milestone 8 Acceptance Report: Gear Auto-Analysis

## Executive Summary
Milestone 8 implements the passive gear auto-analysis engine for Path of Exile 2. It features item tooltip parsing with multi-capture stability corroboration (`VERIFIED` vs `SINGLE_SOURCE` vs `CONFLICTING`), deterministic SHA-256 item hashing, gear freshness tracking with configurable TTL (default 1800s), current-versus-target build evaluation, progression milestone investment advice, observable mechanic conflict detection (attribute deficits, archetype mismatches, CI with chaos resist, EB with life regen), and guided slot-by-slot audit storage with CLI subcommands. All operations remain strictly read-only with zero game input automation and zero memory mutation.

## Key Deliverables Implemented
1. **Gear Domain Schemas & Deterministic Hasher** (`companion/gear/schema.py`, `companion/gear/hasher.py`):
   - `ItemSlot`, `ItemRarity`, `EquippedItem`, `GearAuditState`, `GearComparisonResult`, `InvestmentAdvice`, `MechanicConflict`.
   - `compute_item_hash`: deterministic SHA-256 computed on a canonical UTF-8 JSON dictionary sorted by slot, name, base_type, rarity, item_level, implicit/explicit mods, and sockets.
2. **Tooltip Parser & Stability Verification** (`companion/gear/tooltip.py`):
   - `parse_item_tooltip`: robust regex-based extraction of name, base type, rarity, requirements (level, str, dex, int), implicit/explicit mods, sockets, and rune sockets.
   - `verify_tooltip_stability`: corroboration across consecutive captures requiring agreement before marking items as `VERIFIED`.
3. **Gear Evaluator, Investment Advisor & Mechanic Conflicts** (`companion/gear/evaluator.py`, `companion/gear/advisor.py`, `companion/gear/conflicts.py`):
   - `evaluate_gear_staleness`: compares item observation timestamp against configured TTL to isolate stale audits.
   - `compare_equipped_against_target` & `compare_candidate_upgrade`: calculates weighted affix scores to determine replacement readiness (`UPGRADE` vs `SIDEGRADE` vs `KEEP`).
   - `generate_investment_advice`: flags items needing upgrade before progression milestones (e.g., Level 52 weapon/resistance swap).
   - `detect_mechanic_conflicts`: detects unmet attribute requirements, weapon archetype mismatches, and passive/gear anti-synergies.
4. **Guided Audit Store & CLI Subcommands** (`companion/gear/audit.py`, `companion/cli.py`):
   - `load_gear_audit_state` & `record_slot_audit`: atomic persistence of gear state to `gear_audit.json` in runtime directory.
   - CLI subcommands:
     - `companion gear status`: displays audited slot summary, staleness, and active mechanic conflicts.
     - `companion gear audit --slot <slot> [--file <path> | --text <text>]`: parses tooltip and records slot audit.
     - `companion gear compare --slot <slot> [--file <path> | --text <text>]`: compares candidate upgrade against equipped gear.

## Verification & Test Results
- Total Tests: 390 passed cleanly in 2.73s.
- `tests/gear/test_schema_and_hasher.py`: 2 passed.
- `tests/gear/test_tooltip.py`: 4 passed.
- `tests/gear/test_evaluator_and_conflicts.py`: 4 passed.
- `tests/cli/test_m8_cli.py`: 3 passed.
- `tests/test_m8_integration.py`: 1 passed (full multi-capture corroboration, deterministic hashing, persistence reload, TTL staleness, upgrade advice, attribute conflict).
- Static No-Input Compliance (`tests/compliance/test_no_input_guard.py`): 9 passed, 0 violations.
- Canonical OpenSpec Specs: 16 passed validation.
