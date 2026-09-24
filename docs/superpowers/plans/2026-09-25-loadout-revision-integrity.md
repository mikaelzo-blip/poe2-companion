# Loadout Revision Integrity & Decision-Relevant Fact Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the final focused remediation for Loadout Revision Integrity in PoE2 Companion, eliminating the stale fact confidence gap, movement speed reconciliation gap, CLI history snapshot bypass, inaccurate CLI wording, and incorrect handling of conflicting character facts.

**Architecture:**
1. Separate loadout structural consistency (revision and fingerprint anchoring) from per-fact usability.
2. Centralize decision-relevant fact dependency determination (`RecommendationFactDependencies`) so only facts materially required for an equipment swap gate recommendation confidence, preventing unrelated stale facts from overblocking clean upgrades.
3. Treat local defense losses (Armour, Evasion, Energy Shield) as deterministic regressions and multidimensional trade-offs (`MIXED_TRADEOFF` / `CONDITIONAL_UPGRADE`) rather than masking them behind Life/resistance gains or scalar weights.
4. Correctly project or stale-mark Movement Speed during baseline reconciliation (`DERIVED_CALCULATION`), and route CLI promotion through history-preserving transition execution.

**Tech Stack:** Python 3.11+, Pydantic v2, Argparse, Pytest, OpenSpec.

**Spec:** `openspec/changes/poe2-companion-equipment-intelligence/specs/equipment-intelligence/spec.md`

## Global Constraints

- Do NOT discard existing loadout revision, fingerprint, or history snapshot implementation.
- Do NOT mutate `runtime/equipment_uat_live_v2`.
- Do NOT touch or stage `openspec/changes/poe2-companion-development-observation-mode/**`.
- Do NOT push to remote. Do NOT archive the OpenSpec change.
- Do NOT redefine `check_baseline_consistency()` to mean "every stat is fresh" — keep revision and fingerprint anchoring semantics intact.
- Do NOT invent arbitrary point weights or fake defense-to-life conversion formulas.
- Passive, read-only compliance: strictly zero simulated inputs, zero memory reading, zero game client manipulation.

## Review Focus

1. `CharacterFact.is_known`: `VerificationState.CONFLICTING` must evaluate to `False` (unusable/not known).
2. Defense-dependent decision with stale baseline Armour: candidate changing local Armour must NOT emit `EQUIP_NOW`; uncertainties must explicitly mention stale Armour.
3. Defense-independent upgrade: candidate ring changing only known Life/resistances must NOT be blocked merely because unrelated Armour/Evasion/ES are stale.
4. Fresh local defense loss (800 -> 0 Armour) with Life gain: must evaluate to a real defense regression / trade-off (`CONDITIONAL_UPGRADE`), never clean `DOMINANT_IMPROVEMENT` / `EQUIP_NOW`.
5. Movement speed reconciliation during promotion: must compute `old_ms - disp_ms + cand_ms` with `BaselineSource.DERIVED_CALCULATION` when known, or mark `STALE` without fabricating values.
6. CLI `promote-candidate`: must route through history-preserving wrapper, incrementing revision exactly once and creating exactly one revision snapshot in `loadout_history`.

---

### Task 1: Fix Canonical Fact Predicate `CharacterFact.is_known`

**Files:**
- Modify: `companion/equipment/baseline.py:40-46`
- Test: `tests/unit/equipment/test_loadout_revision_integrity.py`

**Interfaces:**
- Consumes: `VerificationState` from `companion.state.provenance`.
- Produces: Corrected `CharacterFact.is_known` property excluding `CONFLICTING`, `UNKNOWN`, and `STALE`.

- [ ] **Step 1: Write the failing test**

In `tests/unit/equipment/test_loadout_revision_integrity.py`, add:
```python
def test_character_fact_conflicting_is_not_known():
    fact = CharacterFact[int](
        value=50,
        source=BaselineSource.MANUAL_USER_INPUT,
        observed_at="2026-09-25T00:00:00Z",
        verification=VerificationState.CONFLICTING,
    )
    assert fact.is_known is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/equipment/test_loadout_revision_integrity.py::test_character_fact_conflicting_is_not_known -v`
Expected: FAIL (`assert True is False`)

- [ ] **Step 3: Implement minimal code fix**

In `companion/equipment/baseline.py`:
```python
    @property
    def is_known(self) -> bool:
        return self.value is not None and self.verification not in (
            VerificationState.UNKNOWN,
            VerificationState.STALE,
            VerificationState.CONFLICTING,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/equipment/test_loadout_revision_integrity.py::test_character_fact_conflicting_is_not_known -v`
Expected: PASS

---

### Task 2: Movement Speed Baseline Reconciliation & Decision Safety

**Files:**
- Modify: `companion/equipment/reconciler.py:180-186`
- Test: `tests/unit/equipment/test_reconciler.py`, `tests/unit/equipment/test_loadout_revision_integrity.py`

**Interfaces:**
- Consumes: `ItemContribution.movement_speed_delta`, `baseline.movement_speed`.
- Produces: Reconciled `CharacterStatBaseline.movement_speed` as `DERIVED_CALCULATION` when known, or `STALE` when unproven.

- [ ] **Step 1: Write the failing test**

In `tests/unit/equipment/test_loadout_revision_integrity.py`:
```python
def test_movement_speed_reconciliation_promotion():
    base = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="c1",
        anchored_loadout_revision=1,
        movement_speed=7,
    )
    disp = ItemContribution(
        item_id="i1",
        slot=SlotType.BOOTS,
        slot_occupancy=SlotOccupancy.SINGLE_SLOT,
        slot_conflict_topology=SlotConflictTopology(occupied_slots=[SlotType.BOOTS], conflicting_slots=[SlotType.BOOTS], is_known=True),
        movement_speed_delta=10.0,
    )
    cand = ItemContribution(
        item_id="i2",
        slot=SlotType.BOOTS,
        slot_occupancy=SlotOccupancy.SINGLE_SLOT,
        slot_conflict_topology=SlotConflictTopology(occupied_slots=[SlotType.BOOTS], conflicting_slots=[SlotType.BOOTS], is_known=True),
        movement_speed_delta=25.0,
    )
    reconciled = reconcile_baseline_after_swap(
        baseline=base,
        displaced_contributions=[disp],
        candidate_contribution=cand,
        new_loadout_revision=2,
    )
    assert reconciled.movement_speed.value == 22
    assert reconciled.movement_speed.source == BaselineSource.DERIVED_CALCULATION
    assert reconciled.movement_speed.verification == VerificationState.VERIFIED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/equipment/test_loadout_revision_integrity.py::test_movement_speed_reconciliation_promotion -v`
Expected: FAIL (`assert 7 == 22`)

- [ ] **Step 3: Implement minimal code fix**

In `companion/equipment/reconciler.py`:
Compute net movement speed delta:
```python
    disp_ms = sum(c.movement_speed_delta for c in displaced_contributions)
    cand_ms = candidate_contribution.movement_speed_delta if candidate_contribution else 0.0
    net_ms = cand_ms - disp_ms

    if baseline.movement_speed.is_known and baseline.movement_speed.value is not None:
        new_ms_fact = CharacterFact[int](
            value=int(baseline.movement_speed.value + net_ms),
            source=BaselineSource.DERIVED_CALCULATION,
            observed_at=now_iso,
            verification=VerificationState.VERIFIED,
        )
    elif baseline.movement_speed.value is not None:
        new_ms_fact = baseline.movement_speed.mark_stale()
    else:
        new_ms_fact = baseline.movement_speed
```
Pass `movement_speed=new_ms_fact` when constructing `CharacterStatBaseline`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/equipment/test_loadout_revision_integrity.py::test_movement_speed_reconciliation_promotion -v`
Expected: PASS

---

### Task 3: Centralize Decision-Relevant Fact Dependencies & Per-Fact Sufficiency

**Files:**
- Create: `companion/equipment/fact_dependencies.py`
- Modify: `companion/equipment/data_sufficiency.py`, `companion/equipment/engine.py`
- Test: `tests/unit/equipment/test_data_sufficiency.py`, `tests/unit/equipment/test_loadout_revision_integrity.py`

**Interfaces:**
- Consumes: `ItemCandidate`, `loadout`, `slot`, `cascade_result`, `projection`.
- Produces: `RecommendationFactDependencies`, `DataSufficiencyResult` with targeted per-fact freshness checks.

- [ ] **Step 1: Write failing tests for defense-dependent vs defense-independent sufficiency**

In `tests/unit/equipment/test_loadout_revision_integrity.py`:
```python
def test_stale_armour_blocks_armour_changing_candidate():
    # Current body armour 800 armour, candidate 0 armour
    # Baseline armour is STALE
    # Expected: data sufficiency reports stale armour, is_sufficient_for_equip_now is False
    ...

def test_stale_armour_does_not_block_defense_independent_ring():
    # Stale Armour / Evasion / ES
    # Candidate ring changes only Life & Fire Res
    # Expected: is_sufficient_for_equip_now is True
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/equipment/test_loadout_revision_integrity.py::test_stale_armour_blocks_armour_changing_candidate tests/unit/equipment/test_loadout_revision_integrity.py::test_stale_armour_does_not_block_defense_independent_ring -v`
Expected: FAIL

- [ ] **Step 3: Implement `companion/equipment/fact_dependencies.py` and update `data_sufficiency.py`**

Define `determine_recommendation_fact_dependencies(...)` deriving:
- `needs_armour`: `cand.local_armour != disp_armour` or candidate has armour mods/mechanics.
- `needs_evasion`: `cand.local_evasion != disp_evasion` or candidate has evasion mods/mechanics.
- `needs_energy_shield`: `cand.local_energy_shield != disp_es` or candidate has ES mods.
- `needs_movement_speed`: `cand_ms != disp_ms`.
- `needs_strength`: `cand_str != disp_str` or candidate/cascade requires Strength.
- `needs_dexterity`: `cand_dex != disp_dex` or candidate/cascade requires Dexterity.
- `needs_intelligence`: `cand_int != disp_int` or candidate/cascade requires Intelligence.
- `needs_life`: `cand_life != disp_life`.
- `needs_fire_res`, `needs_cold_res`, `needs_lightning_res`, `needs_chaos_res`: candidate changes res or resistance evaluation evaluates deficits.

In `analyze_data_sufficiency`:
For each needed fact, check if baseline fact is usable (`is_known`). If UNKNOWN, STALE, or CONFLICTING:
- Add specific explanatory reason: `"Armour baseline is STALE and this candidate changes local Armour. Exact resulting character Armour cannot be safely projected."` or `"Movement Speed is unknown and this swap changes Movement Speed."` or `"Strength is conflicting and is required to validate equipment/gem requirements."`
- Mark `is_sufficient_for_equip_now = False`, `sufficiency = RecommendationDataSufficiency.INSUFFICIENT_FOR_CONFIDENT_EQUIP`.
Unneeded facts that are stale DO NOT block `is_sufficient_for_equip_now`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/equipment/test_loadout_revision_integrity.py -v`
Expected: PASS

---

### Task 4: Deterministic Local Defense Trade-Off Semantics & Mixed Defenses

**Files:**
- Modify: `companion/equipment/precedence.py`, `companion/equipment/engine.py`
- Test: `tests/unit/equipment/test_precedence.py`, `tests/unit/equipment/test_loadout_revision_integrity.py`

**Interfaces:**
- Consumes: `projection`, `contextual_analysis`.
- Produces: Multidimensional comparison with defense regression detection returning `Verdict.CONDITIONAL_UPGRADE` with `flags=["MIXED_TRADEOFF"]`.

- [ ] **Step 1: Write the failing test**

In `tests/unit/equipment/test_loadout_revision_integrity.py`:
```python
def test_fresh_defense_tradeoff_armour_drop_with_life_gain():
    # Fresh baseline Armour 1000
    # Current body armour 800 armour
    # Candidate body armour 0 armour, +80 Life, +10 Fire Res
    # Expected: Verdict is CONDITIONAL_UPGRADE (MIXED_TRADEOFF), not EQUIP_NOW / DOMINANT_IMPROVEMENT
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/equipment/test_loadout_revision_integrity.py::test_fresh_defense_tradeoff_armour_drop_with_life_gain -v`
Expected: FAIL (emitted `EQUIP_NOW`)

- [ ] **Step 3: Implement defense regression detection in comparison and precedence**

In `companion/equipment/precedence.py` & `companion/equipment/engine.py`:
1. Check if candidate incurs a negative delta on local defenses:
   `has_defense_regression = (armour_delta < 0 or evasion_delta < 0 or es_delta < 0)`
2. If `has_defense_regression`:
   Candidate cannot qualify for clean `RESOLVES_DEFICIT` / `IMPROVES_DEFICIT` / `DOMINANT_IMPROVEMENT` to produce `EQUIP_NOW`.
   Set comparison to `MultidimensionalComparison.MIXED_TRADEOFF`.
   Verdict evaluates to `Verdict.CONDITIONAL_UPGRADE` with `flags=["MIXED_TRADEOFF"]` and trade-off reason.
3. If candidate loses Armour but gains Evasion (or vice-versa), treat as `MIXED_TRADEOFF`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/equipment/test_loadout_revision_integrity.py::test_fresh_defense_tradeoff_armour_drop_with_life_gain -v`
Expected: PASS

---

### Task 5: Route CLI Promotion Through Authoritative Wrapper and Fix CLI Wording

**Files:**
- Modify: `companion/cli.py:1280-1345`, `companion/equipment/loadout_cli.py:210-252`
- Test: `tests/unit/equipment/test_loadout_revision_integrity.py`, `tests/unit/equipment/test_loadout_cli.py`

**Interfaces:**
- Consumes: CLI args for `loadout set-clipboard`, `loadout clear`, `loadout promote-candidate`.
- Produces: Correct snapshot creation in `loadout_history` upon promotion, state-accurate stdout messages.

- [ ] **Step 1: Write the failing test**

In `tests/unit/equipment/test_loadout_revision_integrity.py`:
```python
def test_cli_promote_candidate_creates_history_snapshot(tmp_path: Path):
    # Setup finalized loadout rev 1
    # Run CLI promote-candidate
    # Verify rev 1 snapshot exists in runtime/loadout_history/{char_id}/rev_000001.json
    # Verify current loadout is rev 2
    # Verify no duplicate snapshot or double increment
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/equipment/test_loadout_revision_integrity.py::test_cli_promote_candidate_creates_history_snapshot -v`
Expected: FAIL

- [ ] **Step 3: Implement CLI routing and wording updates**

1. In `companion/equipment/loadout_cli.py`:
   Ensure `run_loadout_promote_candidate` attaches `LoadoutTransitionResult` to `new_loadout.last_transition` and properly snapshots `rev N` before advancing to `rev N+1`.
2. In `companion/cli.py`:
   Route `handle_gear_loadout` for `promote-candidate` through `run_loadout_promote_candidate`.
   Format CLI output depending on `trans.is_finalized` and `trans.is_changed`:
   - Finalized & changed:
     `Slot '{args.slot}' updated.\nLoadout revision: {trans.previous_revision} -> {trans.new_revision}.\nExisting baseline is now stale and requires re-baseline.`
   - Finalized & unchanged (no-op):
     `Slot '{args.slot}' unchanged.\nLoadout revision remains {trans.new_revision}.`
   - Draft:
     `Slot '{args.slot}' updated in loadout draft for character '{char_id}'.`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/equipment/test_loadout_revision_integrity.py::test_cli_promote_candidate_creates_history_snapshot -v`
Expected: PASS

---

### Task 6: Update OpenSpec Documentation

**Files:**
- Modify: `openspec/changes/poe2-companion-equipment-intelligence/design.md`
- Modify: `openspec/changes/poe2-companion-equipment-intelligence/specs/equipment-intelligence/spec.md`
- Modify: `openspec/changes/poe2-companion-equipment-intelligence/tasks.md`

**Interfaces:**
- Consumes: Remediation requirements 1-6 from user specification.
- Produces: Strict-valid OpenSpec change artifacts reflecting loadout revision integrity, fact freshness separation, and defense trade-offs.

- [ ] **Step 1: Edit design.md, spec.md, and tasks.md**
Explicitly document:
1. Loadout consistency and per-fact freshness are separate concerns.
2. Decision-relevant stale/unknown/conflicting facts gate confidence.
3. Unrelated stale facts do not globally block recommendations.
4. Local defense regressions are explicit trade-offs, not hidden by Life/resistance gains.
5. Movement Speed reconciliation must project known deltas or mark stale.
6. Every finalized revision transition must preserve history.

- [ ] **Step 2: Validate OpenSpec**
Run: `openspec validate poe2-companion-equipment-intelligence --strict --json`
Expected: `valid: true`, 0 issues.

---

### Task 7: Full Verification Suite, Forensic Recheck, and Clean Local Commit

**Files:**
- Test: All tests in `tests/`
- Staged: Equipment Intelligence remediation files only.

- [ ] **Step 1: Execute isolated end-to-end check in temporary runtime**
Exercise CLI lifecycle: draft -> set equipment -> finalize -> baseline set -> promote candidate -> inspect loadout/history/baseline -> evaluate candidate.
Verify no mutation of `runtime/equipment_uat_live_v2`.

- [ ] **Step 2: Execute full regression test suite**
Run: `uv run pytest -W error`
Run: `uv run pytest tests/compliance/test_no_input_guard.py -v`
Run: `uv run python -m compileall -q companion tests`
Run: `git diff --check`
Run: `openspec validate poe2-companion-equipment-intelligence --strict --json`

- [ ] **Step 3: Forensic Recheck Verification**
Verify points A through F:
A. STALE Armour + candidate changes Armour -> NOT EQUIP_NOW
B. STALE Armour + ring independent of Armour -> Armour alone does not block
C. Fresh current body armour 800, candidate 0 Armour + Life -> defense loss appears as trade-off, NOT clean DOMINANT_IMPROVEMENT
D. Promotion changes MS -> baseline MS correctly derived or stale
E. CLI promote-candidate -> history snapshot created
F. CONFLICTING fact -> not known

- [ ] **Step 4: Create single local commit**
Stage ONLY Equipment Intelligence remediation files.
Do NOT stage `openspec/changes/poe2-companion-development-observation-mode/**`.
Run `git commit -m "fix: enforce loadout revision integrity"`.
Do NOT push. Do NOT archive.
