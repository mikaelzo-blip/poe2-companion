# Design: Post-Overnight Remediation Architecture

## Context

The forensic audit verified four concrete remediation areas:
1. M7 currently lacks real OS screen pixel acquisition, containing only downstream text parsers and classifiers. It conflates capture with extraction without formal layer boundaries.
2. M8 contains an unverified weighted scoring formula (`_compute_item_defensive_score`) with arbitrary weights and magic score delta thresholds.
3. M9 includes unsourced heuristic rules (scaling curves, arbitrary life/chaos formulas, affix thresholds, mana/attribute buffers), labels mechanical rules as monolithically source-backed without operand verification, and attempts to implement story routing and economy optimization features explicitly deferred by Blueprint Section 62.
4. The single-writer cross-process test in `tests/state/test_single_writer.py` emits `ResourceWarning` unclosed file descriptor warnings under strict pytest warnings (`pytest -W error`) and currently relies on flawed cleanup sequencing or magic fixed sleeps.

See `proposal.md` for full motivation and `specs/` for behavioral delta requirements.

## Goals / Non-Goals

**Goals:**
- Implement a minimal, read-only Windows screen and bounded region capture adapter in `companion/vision/capture.py`.
- Formally establish the two-layer boundary: Screen Capture (`OS pixels -> CapturedFrame`) decoupled from Visual Extraction (`CapturedFrame -> structured observation`).
- Establish an immutable `CapturedFrame` pixel contract with explicit format, stride, and provenance fields.
- Formally establish that M7 is capture-capable; without a dedicated image extractor, `CharacterPanelStats` remains `UNKNOWN`, while text parsing remains a separate test/input path.
- Replace invented M8 numeric gear scoring with discrete, factual comparisons against verified build target requirements (`ComparisonVerdict`).
- Require strict operand-level provenance and evidence verification (available, supported structured source, fresh, reliable, adequate scope) for all M9 mechanical rules.
- Remove invented heuristics (2x mana buffer, +5 attribute margin, act resistance formulas, negative chaos threshold, life formulas, affix thresholds) without fabricating missing values.
- Decommission deferred story route and economy optimization features from authoritative runtime and CLI workflows per Blueprint Section 62.
- Protect M4 Objective Engine from consuming pseudo-scores or unverified heuristics for high-severity objectives.
- Provide deterministic subprocess lifecycle (`terminate()` -> `communicate(timeout=5)` / `kill()` -> `communicate(timeout=5)`) and bounded monotonic lock polling in `tests/state/test_single_writer.py` without magic sleeps or warnings under `pytest -W error`.

**Non-Goals:**
- Modifying or re-architecting accepted M0-M6 or M10 baseline components.
- Adding full OCR optical character recognition engines or trained vision models in this remediation (vision capture provides raw pixel frames and region bounding; character panel extraction remains `UNKNOWN` until an extractor is integrated).
- Introducing keyboard, mouse, or window automation capabilities (prohibited by no-input policy).
- Introducing database migrations or persisting unconsented screenshot captures.
- Inventing new quest databases or economy pricing models.
- Modifying production `companion/state/lock.py` unless an actual production defect is discovered.

## Decisions

### 1. Screen Capture Architecture, Layering, and Pixel Contract (`companion/vision/capture.py`)

#### Two-Layer Boundary: Capture vs Visual Extraction
The system explicitly separates visual processing into two decoupled architectural layers:
1. **SCREEN CAPTURE Layer (`OS pixels -> CapturedFrame`)**:
   - Sole responsibility: Acquire raw screen or window pixel buffers from the operating system into an in-memory structured frame.
   - Strictly read-only, non-persistent by default, zero input automation.
   - Successful capture with `mss` proves **ONLY** `CapturedFrame` availability.
2. **VISUAL EXTRACTION Layer (`CapturedFrame -> structured observation`)**:
   - Sole responsibility: Transform raw pixel buffers into structured game domain models (e.g. `CharacterPanelStats`, `TooltipObservation`).
   - The existing regex and text parser (`companion/vision/parser.py`) is a text-string parser, **NOT** a raw-pixel extractor.
   - Since no real optical character recognition (OCR) or computer vision model is integrated in this remediation:
     - `CharacterPanelStats` remains `VerificationState.UNKNOWN` when raw captured pixels are supplied.
     - Text fixtures and manual extracted text remain separate, decoupled test and input paths for downstream parser validation.
     - M7 is described and documented as **capture-capable**, never as performing automatic visual interpretation of raw display pixels.

#### CapturedFrame Pixel Contract
To prevent ambiguous buffer passing and ensure raw pixels are never silently treated as text, `CapturedFrame` implements a rigid pixel contract:
```python
class PixelFormat(str, Enum):
    BGRA = "BGRA"  # Native Windows GDI / DIB / MSS byte order
    RGBA = "RGBA"

@dataclass(frozen=True)
class CaptureRegion:
    left: int
    top: int
    width: int
    height: int

@dataclass(frozen=True)
class CapturedFrame:
    pixels: bytes                # Raw uncompressed pixel byte buffer
    format: PixelFormat          # Pixel format and channel byte order (default: BGRA)
    width: int                   # Frame width in pixels (> 0)
    height: int                  # Frame height in pixels (> 0)
    channels: int                # Number of color channels (4 for BGRA/RGBA)
    row_stride: int              # Bytes per row (width * channels or aligned DIB stride)
    region: CaptureRegion | None # Sub-region coordinates, or None if full monitor
    source_id: str | int         # Monitor index, display device handle, or source ID
    captured_at: str             # ISO 8601 UTC timestamp of frame acquisition
    backend: str                 # Backend provenance tag ("mss" or "fake")

    def __post_init__(self) -> None:
        expected_len = self.row_stride * self.height
        if len(self.pixels) < expected_len:
            raise ValueError(f"Pixel buffer size {len(self.pixels)} smaller than stride * height {expected_len}")
```

#### Read-Only Backend & Isolation
- **Selected Dependency:** `mss>=9.0.0` (~70KB pure-Python/ctypes bindings to Win32 GDI `user32`/`gdi32`, zero input capabilities).
- **Backend Protocol:**
  - `ScreenCaptureBackend(Protocol)`: Defines `capture_screen(source_id: int = 1) -> CapturedFrame` and `capture_region(region: CaptureRegion, source_id: int = 1) -> CapturedFrame`.
  - `MSSCaptureBackend(ScreenCaptureBackend)`: Production backend.
  - `FakeCaptureBackend(ScreenCaptureBackend)`: Test double returning synthetic pixel buffers.
- **Type Safety & Parser Isolation:**
  - Raw pixel buffers and `CapturedFrame` instances cannot be passed directly into string text parsers; calling regex or text parsers with pixel bytes raises a `TypeError`.
- **Persistence & Failure:**
  - Frames remain strictly in-memory. Capture failure (e.g. session lock, permission denial) returns a structured failure with `VerificationState.UNKNOWN`.

### 2. M8 Factual Target-Driven Item Comparison

- **Removal of Invented Scoring:**
  - Delete `_compute_item_defensive_score(item)`.
  - Delete arbitrary weights: `level_req * 0.5`, `life * 1.0`, `fire_res * 1.2`, `cold_res * 1.2`, `lightning_res * 1.2`, `chaos_res * 1.5`.
  - Delete arbitrary replacement thresholds: `level_gap > 20`, `score < 40.0`.
  - Delete `score_delta`, `durability_score`, and score-derived `UPGRADE`/`RETAIN`/`SIDEGRADE` actions.
- **Factual Comparison Engine:**
  - Compare candidate items strictly against explicit verified build requirements supplied by M0/M2/M3 target snapshots (e.g. minimum flat life, specific elemental resistances, base item archetypes, attribute prerequisites).
  - Produce deterministic semantic verdicts (`ComparisonVerdict` enum):
    - `SATISFIES_MORE_VERIFIED_REQUIREMENTS`: Candidate meets all target requirements met by equipped item plus at least one unsatisfied target requirement.
    - `SATISFIES_FEWER_VERIFIED_REQUIREMENTS`: Candidate fails requirements currently satisfied by equipped item.
    - `EQUIVALENT_FOR_KNOWN_REQUIREMENTS`: Both items satisfy the exact same set of verified target requirements.
    - `INCOMPARABLE`: Trade-off present (candidate satisfies requirement X but loses requirement Y), or requirements are disjoint.
    - `UNKNOWN`: Insufficient target requirements or unverified item attributes.
  - If no target requirements exist for the slot: return `UNKNOWN` or `INCOMPARABLE`, never an upgrade verdict.
  - Preserve all observable attributes: item identity, item hash, structured explicit/implicit affixes, runes, sockets, observed timestamp, and TTL staleness.

### 3. M9 Operand Provenance Policy, Rule Disposition, and Deferral Compliance

#### Operand Provenance and Evidence Requirements
Do **NOT** simply apply a monolithic `SOURCE_BACKED` label to compound mechanical formulas such as:
- `unreserved_mana < main_skill_cost`
- `current_attribute < item_requirement`

A mechanical comparison is authoritative **ONLY** when EVERY required operand individually satisfies all five criteria:
1. **Available**: Value is present, non-null, and structurally validated.
2. **From supported structured sources**: Sourced directly from verified structured channels (official API character data, verified passive tree, verified item requirements, verified gem metadata).
3. **Sufficiently fresh**: Observation timestamp is within valid TTL (`is_stale == False`).
4. **Sufficiently reliable**: Verification state is strictly `VERIFIED`.
5. **Within adequate observation scope**: Measured in the active character configuration (matching active weapon swap, currently slotted gems, active aura reservations).

#### Operand Failure Matrix
- `unreserved_mana UNKNOWN` -> Result `UNKNOWN`, no definitive advisory or lockout emitted.
- `main_skill_cost STALE` -> Result `UNKNOWN`, no definitive advisory or lockout emitted.
- `VERIFIED current_strength` + `VERIFIED required_strength` + `current_strength < required_strength` -> Authoritative factual mechanical deficit.
- **Do not invent missing operand values:** If an operand is missing or unverified, it evaluates to `UNKNOWN`; the system SHALL NOT substitute default numbers or fabricate heuristics.

#### Removal of Invented Heuristics
- **Remove 2x Mana Heuristic:** Prune arbitrary `2x` skill cost buffer. Hard mechanical lockout (`unreserved_mana < main_skill_cost`) is retained as authoritative when operands are verified.
- **Remove +5 Attribute Margin Heuristic:** Prune arbitrary `< 5` attribute margin warning. Hard mechanical deficit (`current_attribute < required_attribute`) is retained as authoritative when operands are verified.
- **Remove Act Resistance Curve:** Prune `20 + current_act * 10`. Retain endgame 75% elemental cap as `LABELED_INFERENCE` (`is_inference=True`), never generating critical objectives.
- **Remove Negative Chaos Threshold:** Delete `< -20` threshold.
- **Remove Life Formula:** Delete `level * 35` and `2500` floor.
- **Remove Affix Count:** Delete `< 6` affixes rule.
- **Remove Base Item Level Gap:** Delete `> 20` level gap rule.

#### Rule-by-Rule Classification Table

| Current M9 Rule | Audit Finding | Classification | Action in Remediation |
|---|---|---|---|
| Elemental Resists 75% Endgame Cap | Common game target, but act scaling formula `20 + current_act * 10` is invented | **B. LABELED_INFERENCE** for 75% cap / **D. REMOVE** for act formula | Prune act curve. Retain 75% endgame cap (level 65+) as labeled inference (`is_inference=True`), never emitting critical objectives. |
| Negative Chaos Res `< -20` | Invented arbitrary threshold | **D. REMOVE** | Completely remove threshold and advisory. |
| Life Pool Formula `level * 35` & `2500` floor | Invented arbitrary formula | **D. REMOVE** | Completely remove formula and advisory. |
| Rare Item `< 6` Affixes | Invented PoE1 crafting assumption | **D. REMOVE** | Remove invented rule. |
| Item Level Gap `> 20` | Invented arbitrary threshold | **D. REMOVE** | Completely remove threshold and advisory. |
| Unreserved Mana `< 1x` Cost | Mechanical lockout valid, but requires operand provenance | **A. SOURCE_BACKED (Operand Verified)** | Authoritative ONLY when `unreserved_mana` and `main_skill_cost` are both `VERIFIED`, fresh, and within scope. If either is `UNKNOWN`/`STALE`, yields `UNKNOWN`. |
| Mana Cost Buffer `2x` | Invented arbitrary multiplier | **D. REMOVE** | Completely remove `2x` multiplier heuristic. |
| Attribute Deficit `< required` | Mechanical deficit valid, but requires operand provenance | **A. SOURCE_BACKED (Operand Verified)** | Authoritative ONLY when `current_attribute` and `item_requirement` are both `VERIFIED`, fresh, and within scope. If either is `UNKNOWN`/`STALE`, yields `UNKNOWN`. |
| Attribute Margin `< 5` | Invented arbitrary safety margin | **D. REMOVE** | Completely remove `< 5` margin heuristic. |
| Hardcoded Story Quest Catalog | Blueprint Section 62 deferred feature | **C. DEFERRED_BY_BLUEPRINT** | Decommission `story.py` from runtime and CLI. When queried, return explicit deferred notice. |
| Economy ROI Ordering & Costs | Blueprint Section 62 deferred feature | **C. DEFERRED_BY_BLUEPRINT** | Decommission `economy.py` from runtime and CLI. When queried, return explicit deferred notice. |

### 4. M4 Objective Engine Gating

- The M4 `ObjectiveEngine` and `generate_objective_candidates` SHALL NOT consume removed M8 numeric scores.
- Objectives for gear progression (`STRONG_UPGRADE`, `OPTIMIZATION`) are generated solely from factual missing items or slots identified in M2 build delta (`DeltaStatus.MISSING`) or factual requirement comparison.
- `SURVIVAL_RISK` candidates SHALL NOT be generated from unsourced heuristics. Gating condition: a `SURVIVAL_RISK` objective is emitted ONLY when backed by an authoritative, evaluable `USABLE` rule with verified provenance and verified operand evidence.

### 5. Deterministic Single-Writer Test Cleanup (`tests/state/test_single_writer.py`)

#### Problem with Prior Sequence
Closing `proc.stdout` and `proc.stderr` before process termination causes deadlocks if the child process is blocked writing to full pipe buffers, and fails to drain remaining bytes, leading to `ResourceWarning` unclosed handle warnings or hanging processes.

#### Deterministic Subprocess Lifecycle
The cleanup sequence uses the standard deterministic subprocess lifecycle:
```python
if proc.poll() is None:
    proc.terminate()

try:
    proc.communicate(timeout=5)
except subprocess.TimeoutExpired:
    proc.kill()
    proc.communicate(timeout=5)
```

#### Bounded Monotonic Lock Polling
Following child process exit and pipe closure, parent lock reacquisition must not rely on magic fixed sleeps (such as `time.sleep(0.05)`). Instead, it performs bounded monotonic polling:
```python
deadline = time.monotonic() + 2.0
reacquired = False
while time.monotonic() < deadline:
    try:
        with StateLock(lock_file):
            reacquired = True
            break
    except StateLockError:
        time.sleep(0.01)
assert reacquired, "Lock was not released after child process terminated"
```

#### Lifecycle Guarantees
- **Child Exited**: Guaranteed via `proc.communicate(timeout=5)` (with fallback `kill()` and second `communicate(timeout=5)`).
- **Pipes Drained/Closed**: `communicate()` internally buffers and drains all pipe stdout/stderr streams to EOF and closes the handles.
- **Zero ResourceWarning**: Clean pipe drainage and process reaping prevent unclosed handle warnings under `pytest -W error`.
- **Zero Zombie Processes**: Process exit code is reaped by `communicate()`.
- **No Magic Sleeps**: Replaced with bounded monotonic clock polling.
- **Production Isolation**: Production `companion/state/lock.py` remains unchanged.

## Risks / Trade-offs

- **[Risk] Test suite breakages in legacy M8/M9 tests:** Removing `_compute_item_defensive_score`, `InvestmentAdvice.durability_score`, and `UpgradeComparison.score_delta` will break existing tests expecting those attributes.
  - *Mitigation:* Update tests to assert factual requirement comparison results (`ComparisonVerdict`, matching vs missing requirements) rather than float scores.
- **[Risk] Headless CI environments lack Windows display contexts:** Real screen capture calls may fail on headless CI servers.
  - *Mitigation:* Unit tests use `FakeCaptureBackend`. The real desktop capture test is isolated as an optional smoke test guarded by `@pytest.mark.skipif(not is_desktop_session_available(), reason="...")`.
- **[Risk] Raw pixel frames without OCR:** Users might expect screen capture to automatically populate character stats.
  - *Mitigation:* Explicitly enforce that `CharacterPanelStats` evaluates to `UNKNOWN` until a verified visual extractor exists. M7 is capture-capable, not visual interpretation.
- **[Risk] Strict operand checks increase UNKNOWN outcomes:** When character API data or skill gem data is unavailable or stale, troubleshooting rules yield `UNKNOWN`.
  - *Mitigation:* This is intentional by design. The companion must not emit false alarms or invent missing values when evidence is incomplete or stale.

## Migration Plan

1. Add `mss>=9.0.0` to `pyproject.toml` dependencies.
2. Implement `companion/vision/capture.py` defining the `CapturedFrame` pixel contract, `CaptureRegion`, protocols, and backends (`MSSCaptureBackend`, `FakeCaptureBackend`).
3. Enforce the two-layer boundary: decouple text parsing from raw pixel capture; verify that passing raw pixels to text parsers raises `TypeError`, and verify that `CharacterPanelStats` evaluates to `UNKNOWN` without an extractor.
4. Refactor `companion/gear/advisor.py` to remove weighted scoring and implement `ComparisonVerdict`.
5. Refactor `companion/intelligence/` to implement operand provenance checks, prune unverified heuristics (2x mana buffer, +5 attribute margin, act curves, life/chaos formulas), label inferences, and decommission deferred story/economy modules.
6. Update `tests/state/test_single_writer.py` with deterministic `terminate()` -> `communicate()` lifecycle and bounded monotonic lock polling.
7. Update integration tests and CLI handlers to reflect factual comparisons, operand provenance requirements, and deferred notices.
8. Run `uv run pytest -W error` and compliance checks.
