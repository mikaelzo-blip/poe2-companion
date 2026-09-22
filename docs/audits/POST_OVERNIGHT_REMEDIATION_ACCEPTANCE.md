# Post-Overnight Remediation Acceptance Report

## Acceptance Decision

**Local remediation acceptance: PASS.**

All approved remediation items for deterministic single-writer subprocess cleanup, M7 read-only screen capture backend and layer separation, M8 removal of unsourced numeric gear scoring, and M9 intelligence provenance cleanup with deferred story/economy behavior are fully implemented, verified, and passing under strict `-W error` testing.

---

## 1. Implementation Commit

- **Commit SHA**: `dc7d424af811533954a4a5a165178d86097ea2a6` (`dc7d424`)
- **Message**: `feat: remediate vision gear and intelligence provenance`

---

## 2. Files and Dependencies Changed

### Dependency Changes
- Added `mss>=9.0.0` in `pyproject.toml`
- Updated `uv.lock` with `mss 9.0.2` and related metadata

### Implementation & Test Files Changed (27 files, +1180 / -450 lines)
- `companion/cli.py`: Updated gear comparison output to report requirement matching status instead of numeric score deltas; updated story and economy commands to report blueprint-deferred status.
- `companion/gear/__init__.py`: Exported `ComparisonVerdict`.
- `companion/gear/advisor.py`: Removed `_compute_item_defensive_score`, arbitrary weights, and magic score thresholds; implemented factual build-target requirement comparisons.
- `companion/gear/schema.py`: Added `ComparisonVerdict` enum; removed `durability_score` from `InvestmentAdvice` and `score_delta` from `UpgradeComparison`.
- `companion/intelligence/__init__.py`: Cleaned up public exports, removing direct authoritative story/economy rule exports.
- `companion/intelligence/economy.py`: Decommissioned authoritative rules per Blueprint Section 62, returning explicit `DEFERRED_BY_BLUEPRINT` status.
- `companion/intelligence/gear_rules.py`: Removed rare affix (<6) and item level gap (>20) heuristics.
- `companion/intelligence/schema.py`: Added `DEFERRED_BY_BLUEPRINT` provenance category.
- `companion/intelligence/story.py`: Decommissioned authoritative story rules per Blueprint Section 62, returning `DEFERRED_BY_BLUEPRINT`.
- `companion/intelligence/survival.py`: Removed act resistance curve, negative chaos threshold, and life-by-level heuristic; retained endgame 75% cap as labeled inference (`is_inference=True`).
- `companion/intelligence/troubleshooting.py`: Implemented strict operand provenance and evidence verification; removed 2x mana buffer and <5 attribute margin; evaluates to `UNKNOWN` when operands are missing or unverified.
- `companion/vision/__init__.py`: Exported capture backend, `CapturedFrame`, `PixelFormat`, and `CaptureRegion`.
- `companion/vision/capture.py` (new): Created `CapturedFrame` contract, `ScreenCaptureBackend` protocol, `MSSCaptureBackend`, and `FakeCaptureBackend`.
- `companion/vision/parser.py`: Added strict type assertions prohibiting `CapturedFrame` or raw `bytes` from being treated as text.
- `tests/cli/test_m9_cli.py`: Updated CLI tests to assert deferred blueprint status for story and economy commands.
- `tests/compliance/test_no_input_guard.py`: Added strict compliance test for `companion.vision.capture`.
- `tests/gear/test_evaluator_and_conflicts.py`: Updated gear advisor tests to assert `ComparisonVerdict` and factual requirement matching.
- `tests/intelligence/test_gear_and_troubleshooting.py`: Updated tests for operand provenance, stale operand handling, and heuristic removal.
- `tests/intelligence/test_story_and_economy.py`: Verified `DEFERRED_BY_BLUEPRINT` responses.
- `tests/intelligence/test_survival_rules.py`: Verified heuristic removal and endgame 75% cap labeled inference.
- `tests/objectives/test_generator.py`: Verified M4 objective generator gating prevents unverified heuristics from generating high-priority objectives.
- `tests/state/test_single_writer.py`: Refactored subprocess lifecycle and bounded polling to eliminate `ResourceWarning` leaks.
- `tests/test_m8_integration.py`: Updated M8 end-to-end integration test for requirement-based comparison verdicts.
- `tests/test_m9_integration.py`: Updated M9 end-to-end integration test for provenance-verified troubleshooting and deferred story/economy.
- `tests/vision/test_capture_boundary.py` (new): Verified capture/extraction separation, pixel contract, text parser rejection, error handling, and real desktop smoke test.

---

## 3. Exact Removed Scoring and Heuristics

### M8 Gear Scoring Removal
- Removed `_compute_item_defensive_score(item)` entirely.
- Removed arbitrary numeric mod weights: `level_req * 0.5`, `life * 1.0`, `resists * 1.2`, `chaos * 1.5`.
- Removed magic upgrade thresholds: `level_gap > 20`, `score < 40`, and `delta >= 10`.
- Removed `durability_score` from `InvestmentAdvice` and `score_delta` from `UpgradeComparison`.
- Replaced with `ComparisonVerdict`: `SATISFIES_MORE_VERIFIED_REQUIREMENTS`, `SATISFIES_FEWER_VERIFIED_REQUIREMENTS`, `EQUIVALENT_FOR_KNOWN_REQUIREMENTS`, `INCOMPARABLE`, `UNKNOWN`.

### M9 Provenance and Heuristic Removal
- Removed act resistance curve (`20 + current_act * 10`).
- Removed negative chaos resistance threshold (`< -20`).
- Removed fabricated life math (`level * 35`).
- Retained endgame 75% elemental resistance cap as labeled inference (`is_inference=True`).
- Removed rare affix count rule (`< 6` affixes).
- Removed item level gap rule (`> 20` levels below character).
- Removed troubleshooting safety buffers: `2x` mana buffer and `< 5` attribute margin.
- Missing or stale operands strictly evaluate to `UNKNOWN` without defaulting or guessing.
- Story and economy rules decommissioned to `DEFERRED_BY_BLUEPRINT` per Blueprint Section 62.
- Objective generator gates unverified heuristics from emitting `HARD_BLOCKER`, `SURVIVAL_RISK`, `STRONG_UPGRADE`, or `OPTIMIZATION` objectives.

### Single-Writer Subprocess Cleanup
- Removed fixed `time.sleep(0.05)` in lock reacquisition test; replaced with monotonic clock polling (2.0s deadline, 10ms intervals).
- Bounded child process lifecycle (`poll()`, `terminate()`, `communicate(timeout=5)`, `kill()`), eliminating unclosed pipes and `ResourceWarning` leaks under `-W error`.
- Production `companion/state/single_writer.py` remains unchanged.

---

## 4. M7 Capability Boundary & Screen Capture Verification

- **Layer Separation**: Screen Capture (`OS pixels -> CapturedFrame`) is strictly decoupled from Visual Extraction (`CapturedFrame -> structured observation`).
- **Capability Status**: M7 is capture-capable only. No OCR or computer vision capability is falsely claimed.
- **Contract Boundary**: Passing raw pixels or `CapturedFrame` to text parsers raises `TypeError`. Structured visual observation remains `UNKNOWN` until a supported visual extractor supplies evidence.
- **Desktop Smoke Test Status**:
  - **LIVE DESKTOP CAPTURE VERIFIED**: `MSSCaptureBackend` successfully executed live desktop screen capture on display 1 (resolution 2560x1440, 4 channels BGRA) during `test_windows_desktop_real_capture_smoke` and standalone probe.
  - **LOCAL CAPTURE ADAPTER TESTED**: `FakeCaptureBackend` tested and verified for full screen and bounded region capture.

---

## 5. Verification Evidence

### Focused Remediation Suites
- `tests/vision/test_capture_boundary.py`: **6 passed**
- `tests/compliance/test_no_input_guard.py`: **10 passed**
- `tests/state/test_single_writer.py`: **3 passed**
- `tests/gear/test_evaluator_and_conflicts.py`: **4 passed**
- `tests/intelligence/test_gear_and_troubleshooting.py`: **5 passed**
- `tests/intelligence/test_story_and_economy.py`: **2 passed**
- `tests/intelligence/test_survival_rules.py`: **3 passed**
- `tests/objectives/test_generator.py`: **9 passed**
- `tests/test_m8_integration.py`: **1 passed**
- `tests/test_m9_integration.py`: **1 passed**
- Total focused remediation tests: **44 passed, 0 failed**.

### Full Regression Suite
- Command: `uv run pytest -W error`
- Result: **454 passed, 0 failed, 0 warnings** in 3.43s.

### Compliance Suite
- Command: `uv run pytest tests/compliance/test_no_input_guard.py -v`
- Result: **10 passed, 0 failed** (proves zero imports of keyboard, mouse, `SendInput`, hooks, or process memory access across the codebase, including `companion/vision/capture.py`).

### Compilation Cleanliness
- Command: `uv run python -m compileall -q companion tests`
- Result: Clean (0 errors, exit code 0).

### Whitespace & Git Check
- Command: `git diff --check`
- Result: Clean (no trailing whitespace or conflict markers).

### OpenSpec Validation
- Command: `openspec validate --strict poe2-companion-post-overnight-remediation --json`
- Result: **1 passed, 0 failed** (`valid: true`).

---

## 6. Code Review Findings

- All subprocess handling in tests ensures bounded cleanup, proper pipe draining, and zero zombie processes.
- Capture module adheres strictly to read-only OS screen capture and contains zero hooks or input injection code.
- Input validation in tooltip and visual parsers rejects binary frames with explicit `TypeError`.
- All removed scoring algorithms have been verified absent across all production modules and tests.

---

## 7. Deviations

None. All implementation and test work aligns strictly with the remediation proposal and design.

---

## 8. Remaining Blockers

- **External Provider Verification (M10)**: Official GGG OAuth and character API verification requires live provider credentials and registered client credentials, which are external dependencies.
- **Visual Extraction (Future)**: M7 provides the capture abstraction and raw pixel contract; downstream OCR/CV models for character panel extraction remain deferred to subsequent milestones.

---

## 9. Git Status

- Implementation commit: `dc7d424`
- Active OpenSpec change: `poe2-companion-post-overnight-remediation` ready for canonical sync and archive.
