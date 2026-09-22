# Proposal: Post-Overnight Remediation for M7, M8, M9, and Single-Writer Tests

## Why

A forensic audit of the Path of Exile 2 Companion codebase established four material integrity and provenance issues:
1. M7 lacks a real OS screen capture backend adapter, relying only on downstream text parsing and classification without real pixel acquisition, and conflates capture with extraction without formal layer boundaries.
2. M8 relies on an invented weighted defensive scoring formula (`_compute_item_defensive_score`) and magic upgrade thresholds (`level_gap > 20`, `score < 40`, `delta >= 10`) lacking Fubgun guide or Blueprint provenance.
3. M9 contains unsourced heuristic rules (arbitrary resistance formulas, negative chaos thresholds, life scaling math, affix counts, mana/attribute buffers), labels compound mechanical formulas as monolithically source-backed without operand-level verification, and attempts to implement story quest routing and economy optimization features that are explicitly deferred under Blueprint Section 62.
4. The cross-process single-writer test (`tests/state/test_single_writer.py`) suffers from `ResourceWarning` handle leaks under `pytest -W error` and currently relies on an unstaged magic 50ms sleep or premature pipe closure before process termination instead of deterministic synchronization.

Addressing these issues restores strict provenance, replaces invented heuristics with factual target-driven comparisons, defines strict per-operand evidence requirements, introduces a minimal read-only screen capture backend with explicit layer separation and pixel contracts, decommissions deferred features, and provides deterministic test cleanup without breaking accepted M0-M6 and M10 capabilities.

## What Changes

- **M7 Screen Capture vs Visual Extraction Layering and Pixel Contract**:
  - Explicitly decouple visual processing into two separate architectural layers:
    1. **SCREEN CAPTURE**: `OS pixels -> CapturedFrame` (acquires raw OS display pixels into structured memory).
    2. **VISUAL EXTRACTION**: `CapturedFrame -> structured observation` (extracts game domain observations from frames).
  - Explicitly specify that the existing regex and text parser is **NOT** a raw-pixel extractor.
  - In the absence of an integrated OCR/CV model in this remediation:
    - Successful `mss` capture only proves `CapturedFrame` availability.
    - `CharacterPanelStats` remains `UNKNOWN` until a supported visual extractor supplies evidence.
    - Text fixtures and manual extracted text remain separate, decoupled test and input paths.
    - M7 must be described as **capture-capable**, not automatic visual interpretation.
  - Define an immutable `CapturedFrame` pixel contract specifying pixel format/order (`format: PixelFormat` - `BGRA` or `RGBA`), `width`, `height`, `channels`, `row_stride`, `region`, `source_id`, `captured_at`, and `backend`.
  - Add planning tests proving raw captured pixels are never silently treated or parsed as text.
- **M8 Removal of Unsourced Weighted Scoring**: Completely remove `_compute_item_defensive_score`, arbitrary numeric mod weights, and magic upgrade thresholds (`UPGRADE`, `RETAIN`, `SIDEGRADE` based on numeric deltas). Replace with factual, target-driven item evaluation (`ComparisonVerdict`: `SATISFIES_MORE_VERIFIED_REQUIREMENTS`, `SATISFIES_FEWER_VERIFIED_REQUIREMENTS`, `EQUIVALENT_FOR_KNOWN_REQUIREMENTS`, `INCOMPARABLE`, `UNKNOWN`) comparing only against explicit verified target requirements from M0/M2/M3. **BREAKING** for any caller expecting numeric score floats or generic delta verdicts.
- **M9 Operand Provenance Governance and Deferral Compliance**:
  - Require strict per-operand provenance and evidence requirements for EVERY operand in mechanical comparisons (`unreserved_mana < main_skill_cost`, `current_attribute < item_requirement`). Do not simply label these rules as monolithically `SOURCE_BACKED`.
  - An authoritative mechanical comparison requires that all constituent operands be:
    1. Available (present, non-null, structured)
    2. Sourced from supported structured channels (official API, verified passive tree, verified item requirements, verified gem metadata)
    3. Sufficiently fresh (not stale)
    4. Sufficiently reliable (`VERIFIED`)
    5. Within adequate observation scope (matching active weapon swap, slotted gems, active reservations)
  - Enforce failure outcomes: `unreserved_mana UNKNOWN` -> `UNKNOWN` (no definitive advisory); `main_skill_cost STALE` -> `UNKNOWN`; authoritative deficit emitted only when `VERIFIED current_strength + VERIFIED required_strength + current_strength < required_strength`.
  - Remove arbitrary safety buffers: prune the `2x` mana heuristic and the `< 5` attribute margin heuristic. Never invent missing operand values.
  - Prune invented act resistance scaling curve (`20 + current_act * 10`), negative chaos threshold (`< -20`), fabricated life formula (`level * 35`), rare affix count threshold (`< 6`), and outdated base level threshold (`> 20`).
  - Decommission deferred features: Remove/disable hardcoded story quest catalog (`companion/intelligence/story.py`) and advanced economy optimizer (`companion/intelligence/economy.py`) from authoritative runtime and CLI subcommands in accordance with Blueprint Section 62.
  - Enforce M4 Objective Engine gating: Ensure unsourced heuristics cannot generate high-severity objectives (`CRITICAL_MECHANIC_BREAK`, `HARD_BLOCKER`, `SURVIVAL_RISK`, `STRONG_UPGRADE`, `OPTIMIZATION`). `SURVIVAL_RISK` must only be emitted when backed by an authoritative evaluable `USABLE` rule with verified operand evidence.
- **Deterministic Single-Writer Test Subprocess Lifecycle**:
  - Replace flawed cleanup sequences (such as closing `stdout`/`stderr` before process termination) and magic sleeps (`time.sleep(0.05)`) in `tests/state/test_single_writer.py`.
  - Implement the deterministic subprocess lifecycle:
    ```python
    if proc.poll() is None:
        proc.terminate()

    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate(timeout=5)
    ```
  - Follow with bounded monotonic polling for `StateLock` reacquisition (deadline of 2.0s with 10ms intervals).
  - Guarantees child exit, pipes drained/closed, zero `ResourceWarning`, zero zombies, zero magic fixed sleeps, and bounded lock reacquisition. Production `StateLock` remains untouched.

## Capabilities

### New Capabilities
- `vision-capture`: Minimal, read-only Windows screen and region capture adapter with structured failure states, strict no-input isolation, in-memory frame processing, explicit pixel contract, and strict capture-vs-extraction layer separation.
- `gear-analysis-provenance`: Factual, target-driven equipment comparison replacing invented numeric scoring with semantic requirement evaluation against verified build milestones.
- `intelligence-provenance`: Formal provenance classification, per-operand evidence validation for mechanical rules, decommissioning deferred story and economy features, and strictly gating M4 objective emission.

### Modified Capabilities
<!-- None: The remediation capabilities establish strict provenance constraints that supersede and govern previous M7-M9 behaviors without modifying baseline M0-M6 or M10 contracts. -->

## Impact

- **Dependencies**: Adds `mss>=9.0.0` as a lightweight read-only screen capture dependency in `pyproject.toml`. No heavy vision libraries (such as OpenCV or Pillow) are introduced.
- **APIs and Contracts**:
  - `companion.vision.capture`: New module introducing `CaptureRegion`, `PixelFormat`, `CapturedFrame`, `ScreenCaptureBackend`, `capture_screen`, and `capture_region`.
  - `companion.gear.advisor`: Deprecates and removes `_compute_item_defensive_score`, `InvestmentAdvice.durability_score`, and `UpgradeComparison.score_delta`. Introduces requirement-based comparison verdicts.
  - `companion.intelligence`: Decommissions authoritative story and economy evaluation functions. Implements per-operand verification for mechanical troubleshooting rules. Prunes unsourced heuristics from survival, gear, and troubleshooting rules.
  - `companion.cli`: Updates gear analysis and advisor CLI subcommands to display factual requirement matches instead of numeric score deltas; disables or provides deferred notices for `story` and `economy` commands.
- **Tests and Compliance**:
  - All tests must pass under `uv run pytest -W error`.
  - Full compliance maintained with `tests/compliance/test_no_input_guard.py`.
