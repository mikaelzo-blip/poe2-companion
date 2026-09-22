# Tasks: Post-Overnight Remediation Implementation

## 1. Single-Writer Test Deterministic Cleanup

- [ ] 1.1 Update `tests/state/test_single_writer.py` to implement the deterministic subprocess lifecycle (`if proc.poll() is None: proc.terminate()`, followed by `proc.communicate(timeout=5)` with `except subprocess.TimeoutExpired: proc.kill(); proc.communicate(timeout=5)`) and replace magic fixed `time.sleep(0.05)` with bounded monotonic clock polling for `StateLock` reacquisition (deadline of 2.0s with 10ms poll intervals), verifying zero `ResourceWarning` leaks under `uv run pytest -W error tests/state/test_single_writer.py`.
- [ ] 1.2 Add repeated contention and rapid process cleanup test verifying multiple acquire-release cycles across processes with guaranteed pipe draining, process reaping, zero zombies, and zero unclosed file handle warnings.

## 2. M7 Vision Capture Backend Adapter and Layer Separation

- [ ] 2.1 Add `mss>=9.0.0` dependency to `pyproject.toml` and verify dependency installation and availability with `uv sync`.
- [ ] 2.2 Create `companion/vision/capture.py` defining the immutable `CapturedFrame` pixel contract (`pixels: bytes`, `format: PixelFormat` [BGRA/RGBA], `width: int`, `height: int`, `channels: int`, `row_stride: int`, `region: CaptureRegion | None`, `source_id: str | int`, `captured_at: str`, `backend: str`), `ScreenCaptureBackend` protocol, `MSSCaptureBackend`, and `FakeCaptureBackend`.
- [ ] 2.3 Implement the strict two-layer boundary separating Screen Capture (`OS pixels -> CapturedFrame`) from Visual Extraction (`CapturedFrame -> structured observation`), classifying M7 as capture-capable, specifying that successful capture proves only `CapturedFrame` availability, and ensuring text fixtures remain separate test/input paths.
- [ ] 2.4 Add planning tests proving raw captured pixels are never silently treated as text in `tests/vision/test_capture_boundary.py`, asserting that passing `CapturedFrame` or raw pixel bytes to text parsers raises a `TypeError` and that downstream `CharacterPanelStats` evaluates to `UNKNOWN` until a supported visual extractor supplies evidence.
- [ ] 2.5 Implement structured failure handling in `companion/vision/capture.py` returning error status with `VerificationState.UNKNOWN` rather than fabricating visual frames upon capture failure.
- [ ] 2.6 Add input isolation compliance test verifying `companion/vision/capture.py` contains zero imports of keyboard, mouse, `SendInput`, hooks, or process memory access via `uv run pytest tests/compliance/test_no_input_guard.py`.
- [ ] 2.7 Add optional Windows desktop smoke test guarded by `@pytest.mark.skipif` verifying real pixel capture on platforms with an active desktop session.

## 3. M8 Removal of Unsourced Weighted Gear Scoring

- [ ] 3.1 Remove `_compute_item_defensive_score`, arbitrary numeric weights (`level_req * 0.5`, `life * 1.0`, `resists * 1.2`, `chaos * 1.5`), and magic replacement thresholds (`level_gap > 20`, `score < 40`, `delta >= 10`) from `companion/gear/advisor.py`.
- [ ] 3.2 Define `ComparisonVerdict` enum (`SATISFIES_MORE_VERIFIED_REQUIREMENTS`, `SATISFIES_FEWER_VERIFIED_REQUIREMENTS`, `EQUIVALENT_FOR_KNOWN_REQUIREMENTS`, `INCOMPARABLE`, `UNKNOWN`) and implement factual target-driven candidate comparison against verified build requirements.
- [ ] 3.3 Update `InvestmentAdvice` and `UpgradeComparison` models in `companion/gear/schema.py` and `companion/gear/advisor.py` to remove `durability_score` and `score_delta`, surfacing discrete requirement matches and deficits.
- [ ] 3.4 Update CLI gear comparison formatting in `companion/cli.py` to report requirement matching status instead of numeric score deltas.
- [ ] 3.5 Refactor unit and integration tests in `tests/gear/test_evaluator_and_conflicts.py` and `tests/test_m8_integration.py` to verify factual comparison states and confirm zero arbitrary score references remain.

## 4. M9 Rule Classification, Operand Provenance, and Deferral Compliance

- [ ] 4.1 Refactor `companion/intelligence/survival.py` to remove invented act resistance curve (`20 + current_act * 10`), negative chaos threshold (`< -20`), and fabricated life math (`level * 35`), retaining the endgame 75% cap as a labeled inference (`is_inference=True`).
- [ ] 4.2 Refactor `companion/intelligence/gear_rules.py` to remove invented rare affix count (`< 6`) and base item level gap (`> 20`) rules.
- [ ] 4.3 Implement per-operand provenance and evidence verification in `companion/intelligence/troubleshooting.py` for mechanical comparisons (`unreserved_mana < main_skill_cost`, `current_attribute < item_requirement`), enforcing that every operand must be available, from supported structured sources, fresh, reliable (`VERIFIED`), and within adequate observation scope, evaluating to `UNKNOWN` when any operand is missing or stale.
- [ ] 4.4 Remove invented safety buffers (`2x` mana heuristic, `< 5` attribute margin) from `companion/intelligence/troubleshooting.py` and prohibit inventing or defaulting missing operand values, emitting factual deficits only when all required operands are verified.
- [ ] 4.5 Decommission `companion/intelligence/story.py` and `companion/intelligence/economy.py` from authoritative runtime and CLI workflows per Blueprint Section 62, returning explicit deferred feature notices.
- [ ] 4.6 Enforce M4 Objective Engine gating in `companion/objectives/generator.py` so unverified heuristics cannot emit `CRITICAL_MECHANIC_BREAK`, `HARD_BLOCKER`, `SURVIVAL_RISK`, `STRONG_UPGRADE`, or `OPTIMIZATION` candidates, verifying with `tests/objectives/test_generator.py`.
- [ ] 4.7 Update unit and integration tests in `tests/intelligence/` and `tests/test_m9_integration.py` to verify operand provenance evaluation (`UNKNOWN` on missing/stale operands, authoritative on verified operands), heuristic pruning, labeled inference flags, and deferred feature responses.

## 5. End-to-End Regression and Acceptance

- [ ] 5.1 Run compliance suite verifying zero input automation, hook, or process memory violations via `uv run pytest tests/compliance/test_no_input_guard.py -v`.
- [ ] 5.2 Run full test suite under strict warnings via `uv run pytest -W error`.
- [ ] 5.3 Verify codebase compilation cleanliness with `uv run python -m compileall companion tests`.
- [ ] 5.4 Check git diff cleanliness with `git diff --check`.
