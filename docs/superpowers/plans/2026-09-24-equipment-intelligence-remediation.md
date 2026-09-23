# Equipment Intelligence Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate material implementation defects in the Equipment Intelligence engine (`poe2-companion-equipment-intelligence`) by removing scalar weighted score authority, restoring approved public verdict enums, implementing contextual marginal value and deficiency gating (including Case D and stale baseline safety), fixing CLI help crashes, correcting test terminology, and verifying with a comprehensive contextual test matrix.

**Architecture:** Replace numeric aggregate scoring (`score_delta = Life * weight + ...`) with deterministic contextual evaluation. The engine analyzes character baseline state (raw vs effective resistances, current deficits), evaluates candidate effects on deficiencies (`RESOLVES`, `IMPROVES`, `UNCHANGED`, `WORSENS`, `CREATES_NEW_DEFICIENCY`), checks data sufficiency (`SUFFICIENT`, `PARTIAL_SAFE`, `INSUFFICIENT_FOR_CONFIDENT_EQUIP`), and applies strict non-scalar precedence hierarchy with multidimensional comparison (`DOMINANT_IMPROVEMENT`, `MIXED_TRADEOFF`, `NO_MEANINGFUL_CURRENT_GAIN`, `CLEAR_DOWNGRADE`).

**Tech Stack:** Python 3.11+, Pydantic v2, Argparse, Pytest, OpenSpec.

**Spec:** `openspec/changes/poe2-companion-equipment-intelligence/specs/equipment-intelligence/spec.md`

## Global Constraints

- Approved public verdicts ONLY: `EQUIP_NOW`, `CONDITIONAL_UPGRADE`, `KEEP_FOR_LATER`, `REJECT`, `INSUFFICIENT_DATA`.
- Public/production `SIDEGRADE` and `STASH_FOR_LATER` MUST be completely removed, NOT merely aliased.
- Numeric aggregate score MUST NOT determine or influence final verdicts. No public "net score".
- Missing/stale baseline facts (e.g. `projected_absolute is None`) MUST NOT be silently treated as "no deficiency".
- Known critical deficiency remaining unchanged (Case D) MUST block confident `EQUIP_NOW`.
- Do NOT push to remote. Do NOT archive the OpenSpec change.
- Preserve all unrelated files under `openspec/changes/poe2-companion-development-observation-mode/**`.
- Passive, read-only compliance: strictly no simulated inputs or game manipulation.
- Real live UAT is NOT performed in this step; synthetic tests must be labeled "FIXTURE-BASED INTEGRATION TESTS".

## Review Focus

1. Unescaped `%` in argparse help text causes fatal `ValueError: incomplete format` on `--help`.
2. Stale or missing baseline fact allows candidate with attractive generic stats to bypass deficiency check and receive `EQUIP_NOW`.
3. Candidate leaving existing critical resistance deficit unchanged (delta == 0) receives `EQUIP_NOW` due to generic Life/stats.
4. Resistance modifier contextual valuation: identical +30% resistance must produce critical value on deficient character and low value on overcapped character.
5. Attribute modifier contextual valuation: identical +10 Dex must produce critical value on deficit character and low value on surplus character.

---

### Task 1: Fix CLI Help Syntax Error and Verify Argument Parsing

**Files:**
- Modify: `companion/cli.py:309,337`
- Test: `tests/unit/equipment/test_baseline_cli_help.py`

**Interfaces:**
- Consumes: Argparse subcommands for `gear baseline set` and `gear baseline refresh`.
- Produces: Working `--help` output with escaped `%%` format specifiers.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/equipment/test_baseline_cli_help.py
import subprocess
import sys


def test_baseline_set_help_exits_cleanly():
    res = subprocess.run(
        [sys.executable, "-m", "companion.cli", "gear", "baseline", "set", "--help"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "Character Movement Speed %" in res.stdout


def test_baseline_refresh_help_exits_cleanly():
    res = subprocess.run(
        [sys.executable, "-m", "companion.cli", "gear", "baseline", "refresh", "--help"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "Character Movement Speed %" in res.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/equipment/test_baseline_cli_help.py -v`
Expected: FAIL with `ValueError: incomplete format`

- [ ] **Step 3: Write minimal implementation**

In `companion/cli.py`, replace `help="Character Movement Speed %"` with `help="Character Movement Speed %%"` in lines 309 and 337.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/equipment/test_baseline_cli_help.py -v`
Expected: PASS

- [ ] **Step 5: Verify via direct CLI execution**

Run:
`uv run python -m companion.cli gear baseline set --help`
`uv run python -m companion.cli gear baseline refresh --help`
Expected: Both exit 0 with clean help text.

---

### Task 2: Restore Approved Public Verdict Contract & Purge Unapproved Enums

**Files:**
- Modify: `companion/equipment/precedence.py`
- Modify: `companion/equipment/engine.py`
- Modify: `companion/equipment/recommendation.py`
- Test: `tests/unit/equipment/test_schema.py`

**Interfaces:**
- Consumes: `Verdict` enum.
- Produces: Exactly 5 approved members: `EQUIP_NOW`, `CONDITIONAL_UPGRADE`, `KEEP_FOR_LATER`, `REJECT`, `INSUFFICIENT_DATA`. Zero occurrences of `SIDEGRADE` or `STASH_FOR_LATER`.

- [ ] **Step 1: Write the failing test**

```python
# In tests/unit/equipment/test_schema.py or test_precedence.py
from companion.equipment.precedence import Verdict


def test_public_verdict_contract_exact_members():
    expected_members = {
        "EQUIP_NOW",
        "CONDITIONAL_UPGRADE",
        "KEEP_FOR_LATER",
        "REJECT",
        "INSUFFICIENT_DATA",
    }
    actual_members = {v.value for v in Verdict}
    assert actual_members == expected_members
    assert "SIDEGRADE" not in actual_members
    assert "STASH_FOR_LATER" not in actual_members
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/equipment/test_schema.py -k test_public_verdict_contract -v`
Expected: FAIL due to `SIDEGRADE` and `STASH_FOR_LATER` present in `Verdict`.

- [ ] **Step 3: Write minimal implementation**

In `companion/equipment/precedence.py`:
```python
class Verdict(str, Enum):
    EQUIP_NOW = "EQUIP_NOW"
    CONDITIONAL_UPGRADE = "CONDITIONAL_UPGRADE"
    KEEP_FOR_LATER = "KEEP_FOR_LATER"
    REJECT = "REJECT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
```
Update guidance in `companion/equipment/engine.py` to handle `KEEP_FOR_LATER` and remove `STASH_FOR_LATER` and `SIDEGRADE`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/equipment/test_schema.py -k test_public_verdict_contract -v`
Expected: PASS

- [ ] **Step 5: Search codebase to confirm no production usages of SIDEGRADE or STASH_FOR_LATER remain**

---

### Task 3: Implement Data-Sufficiency Analysis Model

**Files:**
- Create: `companion/equipment/data_sufficiency.py`
- Test: `tests/unit/equipment/test_data_sufficiency.py`

**Interfaces:**
- Consumes: `CharacterStatBaseline`, `EquippedLoadout`, `ItemCandidate`, `SlotType`, `BuildBreakerEvaluation`.
- Produces: `RecommendationDataSufficiency` (`SUFFICIENT`, `PARTIAL_SAFE`, `INSUFFICIENT_FOR_CONFIDENT_EQUIP`) and `DataSufficiencyResult` with detailed reasons.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/equipment/test_data_sufficiency.py
from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.data_sufficiency import (
    RecommendationDataSufficiency,
    analyze_data_sufficiency,
)
from companion.equipment.loadout import EquippedLoadout
from companion.equipment.parser import parse_item_text
from companion.equipment.rules import BuildBreakerCertainty, BuildBreakerEvaluation
from companion.equipment.schema import SlotType

SAMPLE_BOOTS = """Item Class: Boots\nRarity: Rare\nTest Boots\n--------\nRequirements:\nLevel: 45\n--------\n+30 to maximum Life\n"""


def test_unknown_slot_yields_insufficient_for_confident_equip():
    cand = parse_item_text(SAMPLE_BOOTS, target_slot=SlotType.BOOTS)
    loadout = EquippedLoadout(character_id="test", revision=1, is_finalized=True)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1", character_id="test", anchored_loadout_revision=1, life=1000
    )
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)

    res = analyze_data_sufficiency(
        baseline=baseline,
        loadout=loadout,
        candidate=cand,
        slot=SlotType.BOOTS,
        safety_eval=safe,
    )
    assert res.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP
    assert any("slot" in r.lower() for r in res.reasons)


def test_stale_baseline_yields_insufficient_for_confident_equip():
    cand = parse_item_text(SAMPLE_BOOTS, target_slot=SlotType.BOOTS)
    loadout = EquippedLoadout(character_id="test", revision=2, is_finalized=True)
    loadout.set_slot(SlotType.BOOTS, cand)
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="b1", character_id="test", anchored_loadout_revision=1, life=1000
    )
    safe = BuildBreakerEvaluation(certainty=BuildBreakerCertainty.VERIFIED_SAFE)

    res = analyze_data_sufficiency(
        baseline=baseline,
        loadout=loadout,
        candidate=cand,
        slot=SlotType.BOOTS,
        safety_eval=safe,
    )
    assert res.sufficiency == RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP
    assert any("stale" in r.lower() for r in res.reasons)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/equipment/test_data_sufficiency.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'companion.equipment.data_sufficiency'`

- [ ] **Step 3: Write minimal implementation**

Create `companion/equipment/data_sufficiency.py` with:
- `RecommendationDataSufficiency`: `SUFFICIENT`, `PARTIAL_SAFE`, `INSUFFICIENT_FOR_CONFIDENT_EQUIP`
- `DataSufficiencyResult` with `sufficiency`, `reasons`, `is_sufficient_for_equip_now: bool`
- `analyze_data_sufficiency(...)` checking target slot knownness, baseline presence and staleness, resistance fact availability, unknown modifier applicability, and slot topology.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/equipment/test_data_sufficiency.py -v`
Expected: PASS

---

### Task 4: Implement Contextual Marginal Value and Deficiency Impact Engine

**Files:**
- Create: `companion/equipment/contextual_value.py`
- Modify: `companion/equipment/resistance.py`
- Test: `tests/unit/equipment/test_contextual_value.py`

**Interfaces:**
- Consumes: `CharacterStatBaseline`, `StatProjection`, requirements.
- Produces:
  - `MarginalValueTier`: `CRITICAL`, `HIGH`, `NORMAL`, `LOW`, `NO_IMMEDIATE_VALUE`, `UNKNOWN`.
  - `DeficiencyImpact`: `RESOLVES`, `IMPROVES`, `UNCHANGED`, `WORSENS`, `CREATES_NEW_DEFICIENCY`, `UNKNOWN`.
  - `ContextualResistanceAnalysis` and `ContextualAttributeAnalysis`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/equipment/test_contextual_value.py
from companion.equipment.baseline import CharacterStatBaseline
from companion.equipment.contextual_value import (
    DeficiencyImpact,
    MarginalValueTier,
    evaluate_contextual_resistance,
    evaluate_contextual_attribute,
)
from companion.equipment.resistance import ResistanceType


def test_resistance_same_item_different_character():
    # Scenario A: Character with 30% Lightning Res, target 75%
    baseline_a = CharacterStatBaseline.create_partial(
        baseline_id="b_a", character_id="char_a", anchored_loadout_revision=1,
        lightning_res=30, lightning_raw=30, max_lightning_res=75
    )
    # +30 Lightning Res improves deficit from 45 to 15
    res_a = evaluate_contextual_resistance(baseline_a, ResistanceType.LIGHTNING, delta=30.0)
    assert res_a.impact == DeficiencyImpact.IMPROVES
    assert res_a.tier in (MarginalValueTier.HIGH, MarginalValueTier.CRITICAL)

    # Scenario B: Character with 105% raw, 75% effective, target 75%
    baseline_b = CharacterStatBaseline.create_partial(
        baseline_id="b_b", character_id="char_b", anchored_loadout_revision=1,
        lightning_res=75, lightning_raw=105, max_lightning_res=75
    )
    # +30 Lightning Res is just more overcap (surplus)
    res_b = evaluate_contextual_resistance(baseline_b, ResistanceType.LIGHTNING, delta=30.0)
    assert res_b.impact == DeficiencyImpact.UNCHANGED
    assert res_b.tier in (MarginalValueTier.LOW, MarginalValueTier.NO_IMMEDIATE_VALUE)


def test_attribute_same_item_different_character():
    # Scenario A: Dex 88, requires 95 (deficit 7). Candidate +10 Dex -> resolves deficit!
    baseline_a = CharacterStatBaseline.create_partial(
        baseline_id="b_a", character_id="char_a", anchored_loadout_revision=1,
        dexterity=88
    )
    attr_a = evaluate_contextual_attribute(baseline_a, "dex", delta=10.0, highest_required=95)
    assert attr_a.impact == DeficiencyImpact.RESOLVES
    assert attr_a.tier in (MarginalValueTier.CRITICAL, MarginalValueTier.HIGH)

    # Scenario B: Dex 180, requires 95 (surplus 85). Candidate +10 Dex -> low value
    baseline_b = CharacterStatBaseline.create_partial(
        baseline_id="b_b", character_id="char_b", anchored_loadout_revision=1,
        dexterity=180
    )
    attr_b = evaluate_contextual_attribute(baseline_b, "dex", delta=10.0, highest_required=95)
    assert attr_b.impact == DeficiencyImpact.UNCHANGED
    assert attr_b.tier == MarginalValueTier.LOW
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/equipment/test_contextual_value.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'companion.equipment.contextual_value'`

- [ ] **Step 3: Write minimal implementation**

Implement `companion/equipment/contextual_value.py`:
- Enums: `MarginalValueTier` and `DeficiencyImpact`.
- Data classes: `ContextualResistanceAnalysis`, `ContextualAttributeAnalysis`, `LoadoutContextualAnalysis`.
- Contextual evaluation functions classifying impact based on `current_value`, `target_value`, `delta`, and projected state.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/equipment/test_contextual_value.py -v`
Expected: PASS

---

### Task 5: Deficiency-Aware Verdict Precedence and Multidimensional Comparison

**Files:**
- Modify: `companion/equipment/precedence.py`
- Modify: `companion/equipment/slots.py`
- Test: `tests/unit/equipment/test_precedence.py`
- Test: `tests/unit/equipment/test_slot_intelligence.py`

**Interfaces:**
- Consumes: `BuildBreakerEvaluation`, `RequirementCascadeResult`, `DataSufficiencyResult`, `LoadoutContextualAnalysis`.
- Produces: `Verdict` determined via deterministic precedence and multidimensional comparison (`DOMINANT_IMPROVEMENT`, `MIXED_TRADEOFF`, `NO_MEANINGFUL_CURRENT_GAIN`, `CLEAR_DOWNGRADE`). No scalar score.

- [ ] **Step 1: Write the failing tests**

```python
# In tests/unit/equipment/test_precedence.py
def test_case_d_unchanged_critical_deficit_blocks_equip_now():
    """Forensic Case D: Candidate with large life but 0 resistance when character has critical deficit."""
    # Build contextual analysis with unchanged critical lightning deficit
    ...
    # Must yield CONDITIONAL_UPGRADE or KEEP_FOR_LATER, never EQUIP_NOW
    verdict, reason, flags = evaluate_contextual_verdict(...)
    assert verdict != Verdict.EQUIP_NOW
    assert "UNCHANGED_CRITICAL_DEFICIT" in flags
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/equipment/test_precedence.py -k test_case_d -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

In `companion/equipment/precedence.py`:
- Remove `score_delta` parameter and all numeric threshold branches.
- Implement strict precedence order:
  1. `VERIFIED_BUILD_BREAKER` -> `REJECT`
  2. Candidate unrecoverable requirement failure -> `REJECT`
  3. Recoverable requirement failure (equipped gear/gems) -> `CONDITIONAL_UPGRADE`
  4. `UNKNOWN_APPLICABILITY` build breaker -> `INSUFFICIENT_DATA` or `CONDITIONAL_UPGRADE` (`HIGH_RISK`)
  5. Insufficient data for confident equip -> `INSUFFICIENT_DATA`
  6. Candidate creates or worsens critical defensive deficiency -> `CONDITIONAL_UPGRADE` or `REJECT`
  7. Known critical deficiency remains completely UNCHANGED (Case D) -> `CONDITIONAL_UPGRADE` or `KEEP_FOR_LATER`
  8. Candidate resolves/improves critical deficiency with no critical regression -> `EQUIP_NOW`
  9. Healthy character comparison:
     - `DOMINANT_IMPROVEMENT` -> `EQUIP_NOW`
     - `MIXED_TRADEOFF` -> `CONDITIONAL_UPGRADE` or `KEEP_FOR_LATER`
     - `NO_MEANINGFUL_CURRENT_GAIN` -> `KEEP_FOR_LATER`
     - `CLEAR_DOWNGRADE` -> `REJECT`
In `companion/equipment/slots.py`:
- Deprecate/remove `compute_slot_score` and scalar summation. Represent slot properties contextually (e.g. movement speed on boots as required property).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/equipment/test_precedence.py -v`
Expected: PASS

---

### Task 6: Refactor Engine and Public Recommendation Output

**Files:**
- Modify: `companion/equipment/engine.py`
- Modify: `companion/equipment/recommendation.py`
- Test: `tests/unit/equipment/test_engine.py`
- Test: `tests/unit/equipment/test_recommendation.py`

**Interfaces:**
- Consumes: All contextual analysis and precedence components.
- Produces: `EquipmentRecommendation` with structured deficiency tracking, explainable tradeoffs, and formatted report without scalar "NET SCORE".

- [ ] **Step 1: Write the failing tests**

```python
# In tests/unit/equipment/test_recommendation.py
def test_report_does_not_contain_net_score():
    report = format_recommendation_report(rec)
    assert "NET SCORE" not in report.upper()
    assert "CRITICAL DEFICIENCIES" in report or "VERDICT" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/equipment/test_recommendation.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

- In `companion/equipment/engine.py`:
  - Wire `check_baseline_consistency`, `analyze_data_sufficiency`, and `evaluate_loadout_contextual_analysis`.
  - Pass contextual facts into precedence evaluation.
  - Delete `score_delta` calculation and slot scalar summation.
- In `companion/equipment/recommendation.py`:
  - Reorder report sections:
    VERDICT
    WHY
    CRITICAL DEFICIENCIES
    DEFICIENCIES RESOLVED
    DEFICIENCIES REMAINING
    NEW DEFICIENCIES
    KNOWN STAT DELTAS
    REQUIREMENT EFFECT
    BUILD-MECHANIC SAFETY
    UNCERTAINTIES
    TRADEOFFS
  - Completely remove any leading "NET SCORE".

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/equipment/test_engine.py tests/unit/equipment/test_recommendation.py -v`
Expected: PASS

---

### Task 7: Replace Score-Based Tests, Correct UAT Terminology, and Add Required Test Matrix

**Files:**
- Modify: `tests/unit/equipment/test_slot_intelligence.py`
- Modify: `tests/unit/equipment/test_resistance_intelligence.py`
- Modify: `tests/integration/equipment/test_uat_*.py`
- Create: `tests/unit/equipment/test_contextual_matrix.py`

**Interfaces:**
- Consumes: Engine and contextual modules.
- Produces: 100% passing tests asserting contextual semantics, zero score thresholds, and verified integration matrix.

- [ ] **Step 1: Write the required contextual matrix tests**

In `tests/unit/equipment/test_contextual_matrix.py`:
- Test 1: Resistance same item / different character (30% vs 105% raw).
- Test 2: Attribute same item / different character (Dex 88/95 vs Dex 180/95).
- Test 3: Critical deficit Case D (Candidate A +45 Lightning vs Candidate B +0 Lightning, +100 Life on Lightning 30/75 character). Candidate B must NOT receive `EQUIP_NOW`.
- Test 4: Healthy character:
  - Candidate C: verified Life + Movement improvement, no regression -> `EQUIP_NOW`.
  - Candidate D: mixed Life gain + resistance loss while safe -> contextual tradeoff (`CONDITIONAL_UPGRADE` or `KEEP_FOR_LATER`).
  - Candidate E: no meaningful current benefit -> `KEEP_FOR_LATER`.
  - Candidate F: clear verified downgrade -> `REJECT`.
- Test 5: Missing / stale baseline gate:
  - Missing baseline or stale baseline prevents confident `EQUIP_NOW`, emitting `INSUFFICIENT_DATA` or `CONDITIONAL_UPGRADE`.

- [ ] **Step 2: Update existing score-based tests and UAT terminology**

- Update `tests/unit/equipment/test_slot_intelligence.py` to test contextual slot priorities instead of numeric weights and `compute_slot_score`.
- Update `tests/unit/equipment/test_resistance_intelligence.py` to assert `DeficiencyImpact` and `MarginalValueTier`.
- In `tests/integration/equipment/test_uat_*.py`:
  - Update docstrings and comments from "Real item UAT" to "FIXTURE-BASED INTEGRATION TESTS".

- [ ] **Step 3: Run the new test matrix and full test suite**

Run: `uv run pytest tests/unit/equipment/test_contextual_matrix.py -v`
Expected: PASS

---

### Task 8: Full Verification, Forensic Code Audit & Local Remediation Commit

**Files:**
- Audit all files in `companion/equipment/`
- Stage only equipment intelligence remediation files.
- Commit locally: `fix: make gear recommendations context aware`

- [ ] **Step 1: Run complete verification commands**

Run:
`uv run pytest -W error`
`uv run pytest tests/compliance/test_no_input_guard.py -v`
`uv run python -m compileall -q companion tests`
`git diff --check`
`openspec validate poe2-companion-equipment-intelligence --strict --json`
`uv run python -m companion.cli gear baseline set --help`
`uv run python -m companion.cli gear baseline refresh --help`

- [ ] **Step 2: Forensic re-audit for prohibited tokens**

Search production code in `companion/` for:
`SIDEGRADE`
`STASH_FOR_LATER`
`score_delta`
`net score`
`SlotEvaluationWeights`
`compute_slot_score`
`marginal_value_score`
Verify that no surviving occurrence determines final verdict.

- [ ] **Step 3: Git stage and commit**

- Confirm `git status` shows unrelated `openspec/changes/poe2-companion-development-observation-mode/**` untouched and unstaged.
- Stage only `companion/` and `tests/` and equipment intelligence docs.
- Create local commit: `fix: make gear recommendations context aware`.
- Do NOT push. Do NOT archive.

- [ ] **Step 4: Output comprehensive 24-point audit report**
