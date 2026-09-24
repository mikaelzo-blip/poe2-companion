# Stage-Aware Resistance Target Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate equipment intelligence resistance semantics by separating max resistance, reference cap, and hard target concepts, implementing stage-aware resistance policy resolution (Fubgun campaign semantics as REFERENCE_ONLY), preventing below-reference-cap campaign resistances from blocking EQUIP_NOW, preserving capped-state and regression protections, updating user-facing output, and implementing the full test matrix (Cases A-F).

**Architecture:** 
1. Distinguish MAX_RESISTANCE (game cap/clamp, 75 unless modified), REFERENCE_CAP (informational distance to normal cap, 75), and HARD_TARGET (gating threshold requiring verified build rule or explicit user target; never silently derived from max_res).
2. Introduce `ResistancePolicyMode` (`REFERENCE_ONLY`, `VERIFIED_HARD_TARGET`, `USER_HARD_TARGET`) and `ResistanceTargetPolicy` with provenance and verification fields. For Fubgun campaign stages (`lvl 1-14`, `lvl 15-32`, `lvl 33-51`), policy is `REFERENCE_ONLY` with `target_effective = None` and `reference_cap = 75`.
3. Centralize policy resolution in `get_resistance_policy` and `resolve_resistance_policies`.
4. In `evaluate_contextual_resistance`, evaluate `REFERENCE_ONLY` without creating false hard-target deficits (`deficit_before = 0`), while tracking reference-cap gaps (`gap_before`), recognizing positive improvements towards cap, flagging regressions (`WORSENS`), and protecting capped state drops (`CREATES_NEW_DEFICIENCY`).
5. In `LoadoutContextualAnalysis` and `precedence.py`, ensure only genuine hard-target deficits trigger `has_unchanged_critical_deficiency` (Rule 7), allowing candidates with Life + Movement to achieve `EQUIP_NOW` in campaign leveling.
6. Update user-facing reports to display `GEAR RESISTANCE PRIORITIES (REFERENCE ONLY)` with `LOW / HIGH GEAR PRIORITY` rather than falsely labeling them critical deficiencies.

**Tech Stack:** Python 3.11+, Pydantic v2, Pytest, OpenSpec.

**Spec:** Remediation specification for Stage-Aware Resistance Target Semantics (`poe2-companion-equipment-intelligence`).

## Global Constraints

- Do NOT archive OpenSpec change.
- Do NOT push to remote.
- Preserve all unrelated files under `openspec/changes/poe2-companion-development-observation-mode/**`.
- Do NOT mutate `runtime/equipment_uat_live_v2`. No live UAT in this task.
- max_resistance = 75 does NOT imply hard_target = 75.
- Do NOT invent arbitrary numeric campaign resistance targets (e.g. 20%, 40%, 50%).
- Canonical test command: `uv run pytest -W error`.
- Single local commit message: `fix: make resistance targets stage aware`.

## Review Focus

1. Campaign candidate (+70 Life, +25 Movement Speed, 0 res) at lvl 15-32 receives `CONDITIONAL_UPGRADE` due to `UNCHANGED_CRITICAL_DEFICIT` because Fire/Cold/Lightning are below 75. (Must receive `EQUIP_NOW`).
2. Campaign candidate (+20 Lightning) at lvl 15-32 has improvement cancelled because Fire/Cold remain unchanged below 75. (Must receive `EQUIP_NOW`).
3. Campaign candidate (-15 Lightning, dropping 20 to 5) has regression ignored because policy is reference-only. (Must flag regression / `WORSENS`).
4. Candidate dropping Lightning from 75 to 45 loses defensive protection. (Must trigger `CREATES_DEFICIENCY`).
5. Explicit hard target (75% Lightning specified by user/rule) left unchanged at 30% fails to block `EQUIP_NOW`. (Must block via `UNCHANGED_CRITICAL_DEFICIT`).

---

### Task 1: Build Progression Stages and Resistance Target Policy Domain Models

**Files:**
- Modify: `companion/equipment/rules.py`
- Modify: `companion/equipment/fubgun_rules.py`
- Modify: `companion/equipment/resistance.py`
- Test: `tests/unit/equipment/test_resistance_policy.py`

**Interfaces:**
- Consumes: `BuildProgressionStage`, `ResistanceType`
- Produces: `ResistancePolicyMode`, `ResistanceTargetPolicy`, `get_resistance_policy`, `resolve_resistance_policies`

- [ ] **Step 1: Write the failing tests for ResistanceTargetPolicy and stage resolution**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement ResistancePolicyMode, ResistanceTargetPolicy, and centralized resolver**
- [ ] **Step 4: Run test to verify it passes**

---

### Task 2: Stage-Aware Contextual Resistance Analysis

**Files:**
- Modify: `companion/equipment/contextual_value.py`
- Test: `tests/unit/equipment/test_contextual_resistance_stage_aware.py`

**Interfaces:**
- Consumes: `ResistanceTargetPolicy`, `ResistancePolicyMode`, `CharacterStatBaseline`
- Produces: `ContextualResistanceAnalysis` (with `gap_before`, `gap_after`, `reference_cap`, `is_hard_target`), `LoadoutContextualAnalysis` (with `unresolved_resistance_priorities`)

- [ ] **Step 1: Write the failing tests for contextual resistance under REFERENCE_ONLY vs HARD_TARGET**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement stage-aware logic in evaluate_contextual_resistance and evaluate_loadout_contextual_analysis**
- [ ] **Step 4: Run test to verify it passes**

---

### Task 3: Propagation in Engine & CLI, Precedence Refinement, and Report Formatting

**Files:**
- Modify: `companion/equipment/engine.py`
- Modify: `companion/equipment/precedence.py`
- Modify: `companion/equipment/recommendation.py`
- Modify: `companion/equipment/clipboard.py`
- Modify: `companion/cli.py`
- Test: `tests/unit/equipment/test_stage_propagation.py`

**Interfaces:**
- Consumes: `resolve_resistance_policies`, `evaluate_loadout_contextual_analysis`
- Produces: `EquipmentIntelligenceEngine.evaluate_candidate(..., stage=..., build_profile=...)`, updated `formatted_report`

- [ ] **Step 1: Write the failing tests for engine stage propagation and report formatting**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement engine propagation, precedence check, and report formatting**
- [ ] **Step 4: Run test to verify it passes**

---

### Task 4: Split/Rewrite Old Case-D Tests and Matrix Test Adjustments

**Files:**
- Modify: `tests/unit/equipment/test_precedence.py`
- Modify: `tests/unit/equipment/test_contextual_matrix.py`
- Modify: `tests/unit/equipment/test_contextual_value.py`

**Interfaces:**
- Updates tests that previously relied on universal hard target 75% fallback to explicitly test explicit hard target vs campaign reference-only.

- [ ] **Step 1: Update old Case D tests to delineate explicit hard target vs campaign reference-only**
- [ ] **Step 2: Run existing tests to verify all pass**

---

### Task 5: Required Test Matrix Implementation (Cases A through F)

**Files:**
- Create: `tests/unit/equipment/test_stage_aware_resistance_matrix.py`

**Interfaces:**
- Exercises CASE A (Campaign Life + Movement), CASE B (Campaign Resistance Improvement), CASE C (Campaign Resistance Regression), CASE D (Capped State Regression), CASE E (Explicit Hard Target), CASE F (No Numeric Build Target).

- [ ] **Step 1: Write tests for Cases A, B, C, D, E, F**
- [ ] **Step 2: Run pytest to verify all matrix tests pass**

---

### Task 6: Verification, Forensic Recheck, Strict Compliance, and Local Commit

**Files:**
- Verify clean state, compileall, no-input guard, strict OpenSpec validation
- Local commit: `fix: make resistance targets stage aware`

- [ ] **Step 1: Run full verification suite (`uv run pytest -W error`, `test_no_input_guard.py`, `compileall`, `git diff --check`, `openspec validate`)**
- [ ] **Step 2: Forensic recheck of Case A and Case E**
- [ ] **Step 3: Confirm `runtime/equipment_uat_live_v2` is untouched**
- [ ] **Step 4: Create single local commit**
- [ ] **Step 5: Produce 25-item report**
