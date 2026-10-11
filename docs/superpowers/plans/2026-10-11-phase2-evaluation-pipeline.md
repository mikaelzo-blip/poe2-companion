# Phase 2 — Guide-Aware Evaluation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every dashboard compare (manual and auto-scan) goes through one function, `evaluation.evaluate`. That function uses the character's active guide for stage, breaker rules and priorities, a server-side slot choice, one PoB2 measurement helper, and a relative-threshold policy. The Fubgun-specific branches in `dashboard_api` are gone.

**Architecture:** New modules sit beside the old ones:
- `builds/priorities.py`, `equipment/safety.py`, `equipment/slot_resolver.py`, `equipment/policy.py`, `equipment/evaluation.py`, `equipment/current_item.py`.
- `Pob2EquipmentSession.measure()`.
- `tactical_advisor` rewritten as veto-only.

`dashboard_api` becomes a thin adapter that flattens `EvaluationResult` into the existing response keys. The legacy Fubgun modules stay until Phase 4, because the CLI watcher (`live_watcher.py`) still uses them.

**Tech Stack:** Python 3.11, pydantic v2, pytest, browser JS without libraries.

**Spec:** `docs/superpowers/specs/2026-10-10-multi-guide-evaluation-design.md` (§5, §6, §9, §10; §8 sidebar only). Carry-overs come from `.superpowers/sdd/2026-10-10-phase1-guide-model/progress.md` and `final-review.md` (M8–M11).

## Global Constraints

- Run tests with `uv run pytest -q`. The suite is green after every task.
- No new dependencies.
- UI copy and user-facing reasons are in Indonesian. Code, comments and logs are in English.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never fetch mobalytics from Python.
- Dependency direction: `evaluation` → (`builds`, `safety`, `slot_resolver`, `pob2_equipment_advisor`, `policy`, `tactical_advisor`, `current_item`). Nothing new imports `dashboard_api`. Nothing new imports `fubgun_*`, `pob2_helmet_advisor`, `rules.BuildProgressionStage` or `engine.EquipmentIntelligenceEngine`.
- Canonical slot names: `Helmet, Body Armour, Gloves, Boots, Amulet, Belt, Ring 1, Ring 2, Weapon 1, Weapon 2, Weapon 1 Swap, Weapon 2 Swap`.
- Policy constants (spec §5.5) in `policy.py`:

  | Constant | Value |
  |---|---|
  | `DPS_UP` | `0.01` |
  | `EHP_FLOOR` | `-0.01` |
  | `EHP_UP` | `0.02` |
  | `DPS_FLOOR` | `-0.005` |
  | `DPS_DOWN` | `-0.01` |
  | `RES_CAP` | `75` |

- No `except: pass` on the evaluation path. Every swallowed exception is logged (spec §9).

### Deviations from the spec, decided while planning

- **Sidebar moves into Phase 2.** The guide/stage dropdowns (spec §8, Phase 3) are rewired in Task 9. `evaluate` reads the per-character assignment, so without them no guide can be chosen and the dashboard would not work at the end of the phase.
- **Topology `clear_slots` apply only to the "after" build.** Spec §6 orders it before "measure before", which would drop the current off-hand from the baseline DPS.
- **Legacy wrappers.**
  - `simulate_item`, `simulate_ring_candidate` and `simulate_ambiguous_1h_weapon` become thin wrappers over `measure`.
  - `simulate_weapon_plan` is untouched: only the Fubgun router in `live_watcher` calls it, and both retire in Phase 4.
  - Tests of the retired Fubgun modules migrate in Phase 4 together with the modules.
- **The Fubgun breaker rule is data.** It ships as a default rule keyed by the mobalytics slug (`builds/known_rules.py`). It is applied on import when the guide has no rules yet, and once to the stored guide.
- **Requirements** use `ItemCandidate.required_*` against the effective level and the baseline attributes. An unknown attribute counts as met.
- **Manual compare UI still sends `slot`**, so manual compares stay slot-locked until Phase 3 fixes the UI (#5 UI, #18). The flattened response `slot` uses the legacy UI keys (`set2_main_hand`, `ring2`, …) until Phase 3. `pob_slot` carries the canonical name.
- **Legacy payload fields** `guide` and `stage` are ignored by the server from Task 8 on.

## Review Focus

1. **No guide assigned, or the assigned guide was deleted.** Use character-only mode: one 1–100 stage, no rules and no priorities, and the policy verdict. No crash. Tested in Task 7.
2. **Manual and auto-scan evaluate at the same time on one PoB2 session.** Neither cancels the other. A stale or failed measurement falls back to the heuristic engine with `engine_reason`. Tested in Tasks 4 and 7.
3. **A non-equippable item is pasted** (jewel, flask, charm, waystone, or an unknown class). Return a clear Indonesian error, not a 500 or a guessed slot. Tested in Task 3.
4. **Level-1 or tiny baselines** (`dps_before == 0`, missing resist keys). No division by zero, and the missing keys are skipped. Tested in Task 5.
5. **A locked slot that does not fit the item** (a ring locked to `Helmet`) and the legacy UI keys (`set2_main_hand`, `ring2`). Map the legacy keys. Reject a mismatch with an Indonesian error. Tested in Task 3.

---

### Task 1: Guide priorities and store hardening

**Files:**
- Create: `companion/builds/priorities.py`
- Modify: `companion/builds/store.py`, `companion/builds/guide.py`, `companion/builds/stages.py` (`_ACT_PAIR`)
- Test: `tests/unit/builds/test_priorities.py`, `tests/unit/builds/test_guide_store.py`, `tests/unit/builds/test_stages.py`

**Interfaces:**
- Produces:
  ```python
  def mod_family(line: str) -> str
      # normalize_modifier(line).modifier_type.value when known and not UNKNOWN_MODIFIER,
      # else the lowercased line with every number/range ("12", "12(10-15)", "+", "%") replaced by "#"
  class PrioritySignal(BaseModel):
      matched: int; total: int
      must_have_missing: list[str]   # stage-item must_have lines whose family is absent
      @property
      def ratio(self) -> float | None  # None when total == 0
  def priority_signal(stage_item: StageItem | None, candidate_lines: list[str]) -> PrioritySignal | None
      # None when stage_item is None or has no mods
  ```
- `load_guide` returns `None` and logs a warning on unreadable JSON or a validation error. `list_guides` skips such files.
- `save_guide`, `set_breaker_rules` and `set_assignment` run under one module-level `threading.Lock` (M11).
- `singular_item_class("Daggers")` returns `"Dagger"`. Unknown plurals ending in `s` lose the `s`; labels in the dict still map exactly.
- `_ACT_PAIR` accepts a second act number only in 1–6 ("Act 2 - 30" no longer reads as acts 2–3).

- [ ] **Step 1: Write the failing tests**

```python
def test_priority_signal_counts_families_and_missing_must_have():
    item = StageItem(slot="Boots", name="Leather Boots", item_class="Boots",
                     mods=["+30 to maximum Life", "25% increased Movement Speed", "+20% to Fire Resistance"],
                     must_have=["25% increased Movement Speed"])
    sig = priority_signal(item, ["+52 to maximum Life", "+31% to Fire Resistance"])
    assert (sig.matched, sig.total) == (2, 3)
    assert sig.must_have_missing == ["25% increased Movement Speed"]
    assert sig.ratio == pytest.approx(2 / 3)

def test_unknown_mod_family_ignores_numbers():
    assert mod_family("Gain 12(10-15) Rage on Hit") == mod_family("Gain 3 Rage on Hit")

def test_priority_signal_none_without_stage_item():
    assert priority_signal(None, ["+5 to Strength"]) is None

def test_corrupt_guide_file_is_skipped(tmp_path):
    save_guide(tmp_path, _profile("ok"))
    (tmp_path / "guides" / "bad.json").write_text("{not json", encoding="utf-8")
    assert load_guide(tmp_path, "bad") is None
    assert [g.slug for g in list_guides(tmp_path)] == ["ok"]

def test_singular_item_class_fallback():
    assert singular_item_class("Daggers") == "Dagger"
    assert singular_item_class("Staves") == "Staff"

def test_act_pair_second_number_bounded():
    assert parse_level_range("Act 2 - 30") != (16, 44, False)
```
(`_profile` is the existing helper in `test_guide_store.py`. If it has another name, reuse that helper.)

- [ ] **Step 2: Run** `uv run pytest tests/unit/builds -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the interfaces above.
- [ ] **Step 4: Run** `uv run pytest tests/unit/builds -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(builds): guide priority signal; tolerate corrupt guide files; lock store writes`

---

### Task 2: Safety gate and Fubgun rule as guide data

**Files:**
- Create: `companion/equipment/safety.py`, `companion/builds/known_rules.py`
- Modify: `companion/builds/guide.py` (`BreakerRule` validation, M10), `companion/dashboard_api.py` (`import_guide_payload` applies known rules)
- Test: `tests/unit/equipment/test_safety.py`, `tests/unit/builds/test_guide_api.py`

**Interfaces:**
- Consumes: `GuideProfile`, `BreakerRule`, `GuideStage.weapon_classes` (Phase 1).
- Produces:
  ```python
  # safety.py
  def breaker_reasons(mod_lines: list[str], profile: GuideProfile | None, level: int | None, slot: str) -> list[str]
      # one reason per matching rule: re.search(rule.pattern, line, re.IGNORECASE) on any line,
      # level >= rule.from_level (None level -> rule applies), slot not in rule.exclude_slots
  def weapon_not_in_guide(item_class: str, profile: GuideProfile | None) -> str | None
      # "Senjata tidak dipakai guide (<item_class>)" when the profile has weapon data and
      # item_class is in no stage's weapon_classes; None otherwise (also for non-weapons / no guide)
  # known_rules.py
  KNOWN_RULES: dict[str, list[BreakerRule]]   # key = mobalytics slug from source_url
  def default_rules_for(source_url: str | None) -> list[BreakerRule]
  ```
- The Fubgun entry, keyed by `"fubgun-flameblast-oil-grenade"`:
  - `pattern`: `r"adds .*fire damage to attacks|gain .*as extra fire damage"`
  - `from_level`: `52`
  - `exclude_slots`: `["Weapon 1", "Weapon 2"]`
  - `reason`: `"Fire damage ke Attack menyalakan Oil Grenade terlalu cepat (Fubgun, lvl 52+)"`
- `BreakerRule`:
  - Every `exclude_slots` entry must be a canonical slot.
  - `from_level` is in 1–100. Otherwise construction raises `ValueError`.
- `import_guide_payload`: when the saved profile has no `breaker_rules`, call `set_breaker_rules(runtime_dir, slug, default_rules_for(profile.source_url))` (only when that list is non-empty).

- [ ] **Step 1: Write the failing tests**

```python
PROBE = ["+40 to maximum Life", "Adds 12 to 22 Fire Damage to Attacks", "+20% to Fire Resistance"]

def test_audit_probe_gloves_rejected_for_fubgun_post_swap(fubgun):   # fubgun fixture: profile with KNOWN_RULES applied
    assert breaker_reasons(PROBE, fubgun, 53, "Gloves") == [KNOWN_RULES["fubgun-flameblast-oil-grenade"][0].reason]

def test_probe_safe_pre_swap_and_in_set1(fubgun):
    assert breaker_reasons(PROBE, fubgun, 40, "Gloves") == []
    assert breaker_reasons(PROBE, fubgun, 60, "Weapon 1") == []

def test_probe_not_vetoed_for_navira(navira):
    assert breaker_reasons(PROBE, navira, 53, "Gloves") == []

def test_weapon_not_in_guide():
    assert weapon_not_in_guide("Bow", fubgun_profile) == "Senjata tidak dipakai guide (Bow)"
    assert weapon_not_in_guide("Crossbow", fubgun_profile) is None
    assert weapon_not_in_guide("Bow", None) is None

def test_breaker_rule_rejects_unknown_slot_and_level():
    with pytest.raises(ValueError): BreakerRule(pattern="x", reason="r", exclude_slots=["helmet"])
    with pytest.raises(ValueError): BreakerRule(pattern="x", reason="r", from_level=0)

def test_import_fubgun_fixture_gets_default_rule(tmp_path):   # in test_guide_api.py
    import_guide_payload({"text": FUBGUN_FIXTURE_TEXT}, tmp_path)
    assert load_guide(tmp_path, "fubgun-flameblast-oil-grenade").breaker_rules[0].from_level == 52
```
Build the `fubgun` and `navira` fixtures from `tests/fixtures/guides/*.json` with `import_guide_payload` into `tmp_path`, then `load_guide`.

- [ ] **Step 2: Run** `uv run pytest tests/unit/equipment/test_safety.py tests/unit/builds -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the interfaces above.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Seed the stored guide once.** Run:
  ```
  uv run python -c "from pathlib import Path; from companion.builds.store import set_breaker_rules; from companion.builds.known_rules import KNOWN_RULES; set_breaker_rules(Path('runtime'), 'fubgun-flameblast-oil-grenade', KNOWN_RULES['fubgun-flameblast-oil-grenade'])"
  ```
  Expected: no output. `runtime/guides/fubgun-flameblast-oil-grenade.json` now has one rule.
- [ ] **Step 6: Commit** `feat(equipment): guide-driven safety gate; Fubgun breaker rule as guide data`

---

### Task 3: Server-side slot resolver

**Files:**
- Create: `companion/equipment/slot_resolver.py`
- Test: `tests/unit/equipment/test_slot_resolver.py`

**Interfaces:**
- Consumes: `ItemCandidate` (`slot`, `slot_occupancy`) from `parse_item_text`, `GuideStage.weapon_classes`, `WeaponTopologyResolver.resolve_topology`.
- Produces:
  ```python
  UI_SLOT_KEYS: dict[str, str]   # canonical -> legacy UI key: "Weapon 1" -> "main_hand", "Weapon 2" -> "off_hand",
                                 # "Weapon 1 Swap" -> "set2_main_hand", "Weapon 2 Swap" -> "set2_off_hand",
                                 # "Ring 1" -> "ring1", "Ring 2" -> "ring2", "Body Armour" -> "body_armour",
                                 # other slots -> lowercase name
  def canonical_slot(name: str) -> str
      # accepts canonical names, UI keys, "weapon_1_swap"/"swap_main_hand" forms; ValueError("Slot tidak dikenal: <name>")
  def item_class_of(raw_text: str) -> str      # singular class from the "Item Class:" line ("" when absent)
  class SlotPlan(BaseModel):
      slot: str                      # canonical
      clear_slots: tuple[str, ...] = ()
  def resolve_slots(candidate: ItemCandidate, item_class: str, stage: GuideStage,
                    locked_slot: str | None = None) -> tuple[list[SlotPlan], str]
      # returns (plans, slot_reason); ValueError with Indonesian text when no slot fits
  ```
- Rules, from spec §5.2:
  - **Weapon sets.** A weapon is `candidate.slot in (MAIN_HAND, OFF_HAND)`. Its sets are those where `item_class in stage.weapon_classes[n]`. If exactly one set matches, use it. Otherwise use sets 1 and 2.
  - **Two-handed** (`SlotOccupancy.TWO_HAND`): the main slot of each set, with `clear_slots` from `WeaponTopologyResolver.resolve_topology(candidate, set).clear_slots`.
  - **Off-hand** (`candidate.slot == OFF_HAND`): the off slot of each set.
  - **Other one-hand weapons:** both hands of each set.
  - **Rings:** `Ring 1` and `Ring 2`.
  - **Other slots:** `normalize_and_validate_pob_slot(candidate.slot)`.
  - **`locked_slot`:**
    - Canonicalise it, then keep only that plan.
    - When it is not among the candidate's possible slots for any set, raise `ValueError("Slot terkunci tidak cocok dengan item")`.
  - **Non-equippable items:** when `parse_item_text` gives no usable slot, or the class is a jewel, flask, charm or waystone, raise `ValueError("Item ini tidak bisa dipasang di slot equipment")`.
- `slot_reason` examples:
  - `"Crossbow dipakai guide di Weapon Set 2"`
  - `"Cincin: dicoba di Ring 1 dan Ring 2"`
  - `"Slot dikunci: Helmet"`

- [ ] **Step 1: Write the failing tests** (stages are taken from the Fubgun and Navira fixtures, as in Task 2):

```python
def test_fubgun_lvl60_crossbow_goes_to_set2(fub60):
    plans, reason = resolve_slots(parse_item_text(CROSSBOW), "Crossbow", fub60)
    assert [p.slot for p in plans] == ["Weapon 1 Swap"]
    assert plans[0].clear_slots == ("Weapon 2 Swap",)
    assert "Weapon Set 2" in reason

def test_fubgun_lvl60_staff_goes_to_set1(fub60):
    assert [p.slot for p in resolve_slots(parse_item_text(STAFF), "Staff", fub60)[0]] == ["Weapon 1"]

def test_one_hand_tries_both_hands(navira30):
    assert [p.slot for p in resolve_slots(parse_item_text(SCEPTRE), "Sceptre", navira30)[0]] == ["Weapon 1", "Weapon 2"]

def test_ring_tries_both_rings_and_lock_is_respected(fub60):
    ring = parse_item_text(RING)
    assert [p.slot for p in resolve_slots(ring, "Ring", fub60)[0]] == ["Ring 1", "Ring 2"]
    assert [p.slot for p in resolve_slots(ring, "Ring", fub60, locked_slot="ring2")[0]] == ["Ring 2"]

def test_lock_mismatch_and_legacy_keys(fub60):
    with pytest.raises(ValueError, match="tidak cocok"):
        resolve_slots(parse_item_text(RING), "Ring", fub60, locked_slot="Helmet")
    assert canonical_slot("set2_main_hand") == "Weapon 1 Swap"

def test_non_equippable_item_raises(fub60):
    with pytest.raises(ValueError, match="tidak bisa dipasang"):
        resolve_slots(parse_item_text(JEWEL_OR_CHARM_TEXT), item_class_of(JEWEL_OR_CHARM_TEXT), fub60)
```
Write `CROSSBOW`, `STAFF`, `SCEPTRE` and `RING` as minimal clipboard texts (`Item Class:`, `Rarity: Rare`, name, base, one mod). For `JEWEL_OR_CHARM_TEXT`, use whichever class `parse_item_text` accepts but cannot slot. If it raises, assert that `resolve_slots` is never reached and that the error message comes from the parser.

- [ ] **Step 2: Run** `uv run pytest tests/unit/equipment/test_slot_resolver.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the interfaces above.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(equipment): server-side slot resolver from guide stage weapons`

---

### Task 4: One PoB2 measurement helper

**Files:**
- Modify: `companion/equipment/pob2_equipment_advisor.py`
- Test: `tests/unit/equipment/test_pob2_measure.py`; adjust `tests/unit/equipment/test_pob2_equipment_advisor.py`, `test_pob2_weapon_simulation.py` and `test_pob2_helmet_advisor.py` only where they pin engine call order

**Interfaces:**
- Produces:
  ```python
  class PobEquipmentDelta:                     # new fields, defaults keep old callers working
      res_before: dict[str, float] = {}        # keys "fire", "cold", "lightning", "chaos"
      res_after: dict[str, float] = {}
  class Pob2EquipmentSession:
      main_group: int | None                   # list_skills()["mainSocketGroup"], set after every import
      def submit_candidate(self, candidate_raw: str, candidate_name: str = "", slot: str = "Helmet",
                           source: str = "manual") -> int
      def is_stale(self, candidate_id: int, source: str = "manual") -> bool
      def measure(self, slot: str, raw: str, candidate_id: int, *, source: str = "manual",
                  clear_slots: tuple[str, ...] = (), candidate_name: str = "") -> PobEquipmentDelta | None
  ```
- `measure` steps, under `_engine_lock`:
  1. Use `xml_set = _set_weapon_set_in_xml(self.xml, 2 if slot.endswith("Swap") else 1)`. Import it into the sandbox, `set_main_skill(self.main_group)` when not `None`, then read `get_defenses` and `calc_stats` (the "before").
  2. When `clear_slots` is set, re-import `_clear_slots_in_xml(xml_set, clear_slots)`.
  3. `equip_item(slot, raw)`, `set_main_skill(self.main_group)`, then read "after".
  4. Restore with `import_build(self.xml)` in `finally`.
  5. Check staleness (per `source`) before the lock, after acquiring it, and before building the delta. Stale returns `None`.
  6. On an engine error, mark the session unhealthy as `simulate_item` does today and return `None`.
- `main_group` is set at the three places that assign `stats_before` after an import (`initialize` mock path, `initialize` live path, `sync_character`).
- `get_primary_socket_group(skill_context=None)` returns `self.main_group` when there is no context. The Fubgun skill-name list is deleted, and `find_socket_group_for_skill` is unchanged.
- Thin wrappers:
  - `simulate_item(slot, raw, cid, name)` returns `measure(slot, raw, cid, candidate_name=name)`.
  - `simulate_ring_candidate` measures `Ring 1` and `Ring 2`, so both legs lock the main skill (#8).
  - `simulate_ambiguous_1h_weapon(target_set)` measures both hands of that set (fixes #7 for Set 2).
  - `simulate_weapon_plan` is unchanged.

- [ ] **Step 1: Write the failing tests.** Use a small fake engine local to this file: `call(action, **kw)` records `(action, kw)`. `get_defenses`/`calc_stats` return one value set before `equip_item` and another after it. `list_skills` returns `{"mainSocketGroup": 3, "groups": []}`.

```python
def test_measure_swap_slot_activates_set2_and_locks_skill(session):
    d = session.measure("Weapon 1 Swap", CROSSBOW, session.submit_candidate(CROSSBOW))
    imports = [kw["xml"] for a, kw in session.sandbox_engine.calls if a == "import_build"]
    assert 'useSecondWeaponSet="true"' in imports[0]
    assert [kw["group"] for a, kw in session.sandbox_engine.calls if a == "set_main_skill"] == [3, 3]
    assert imports[-1] == session.xml                       # restored
    assert d.dps_after > d.dps_before and d.res_before["fire"] == FAKE_FIRE_BEFORE

def test_clear_slots_only_affect_after(session):
    session.measure("Weapon 1", STAFF, session.submit_candidate(STAFF), clear_slots=("Weapon 2",))
    imports = [kw["xml"] for a, kw in session.sandbox_engine.calls if a == "import_build"]
    assert 'name="Weapon 2" itemId="0"' not in imports[0] and 'itemId="0"' in imports[1]

def test_staleness_is_per_source(session):
    manual = session.submit_candidate("a", source="manual")
    session.submit_candidate("b", source="auto")
    assert not session.is_stale(manual, "manual")

def test_restore_runs_when_equip_fails(session_failing_equip):
    assert session_failing_equip.measure("Gloves", GLOVES, 1) is None
    assert session_failing_equip.sandbox_engine.calls[-1][0] == "import_build"

def test_ring_wrapper_locks_skill_on_both_legs(session):
    session.simulate_ring_candidate(RING, session.submit_candidate(RING))
    assert [kw["group"] for a, kw in session.sandbox_engine.calls if a == "set_main_skill"] == [3, 3, 3, 3]
```
The fake baseline XML needs a `<Slot name="Weapon 2" itemId="5"/>` so the clear can be seen.

- [ ] **Step 2: Run** `uv run pytest tests/unit/equipment/test_pob2_measure.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest tests/unit/equipment -q`. Expected: PASS. A pre-existing test that pinned the old call order is updated to the new order. Do not delete it unless it asserted the deleted Fubgun skill list, and list each such case in the report.
- [ ] **Step 5: Commit** `feat(pob2): one measure() helper with weapon-set toggle, skill lock and per-source staleness`

---

### Task 5: Relative-threshold policy

**Files:**
- Create: `companion/equipment/policy.py`
- Test: `tests/unit/equipment/test_policy.py`

**Interfaces:**
- Consumes: `PobEquipmentDelta` (Task 4), `PrioritySignal` (Task 1).
- Produces:
  ```python
  class SlotResult(BaseModel):
      slot: str
      verdict: str                     # EQUIP_NOW | CONDITIONAL_UPGRADE | REJECT | INSUFFICIENT_DATA
      dps_pct: float = 0.0
      ehp_pct: float = 0.0
      gains: list[str] = []
      trade_offs: list[str] = []
      reasons: list[str] = []
      is_empty: bool = False
      delta: PobEquipmentDelta | None = None
  def decide(delta: PobEquipmentDelta, *, unmet_requirements: list[str] = [],
             priority: PrioritySignal | None = None, is_empty: bool = False) -> SlotResult
  def insufficient(slot: str, reason: str) -> SlotResult
  def rejected(slot: str, reasons: list[str]) -> SlotResult
  VERDICT_RANK = {"EQUIP_NOW": 3, "CONDITIONAL_UPGRADE": 2, "INSUFFICIENT_DATA": 1, "REJECT": 0}
  ```
- Rules, applied in order:
  1. Compute `dps_pct = (dps_after - dps_before) / max(dps_before, 1)` and `ehp_pct` the same way.
  2. Find the breached resists: keys present in both `res_before` and `res_after` with `before >= RES_CAP > after`.
  3. **REJECT** when any of these holds:
     - `unmet_requirements`;
     - `dps_pct <= DPS_DOWN and ehp_pct <= 0`;
     - a breached resist with no gain (`dps_pct <= 0 and ehp_pct <= 0`).
  4. **EQUIP_NOW** when `(dps_pct >= DPS_UP and ehp_pct >= EHP_FLOOR) or (ehp_pct >= EHP_UP and dps_pct >= DPS_FLOOR)` and there is no breached resist.
  5. Otherwise **CONDITIONAL_UPGRADE**.
  6. When `priority.must_have_missing` is non-empty, cap the verdict at **CONDITIONAL_UPGRADE**.
- Text formats:
  - DPS and EHP as `f"{dps_pct:+.1%} DPS"` and `f"{ehp_pct:+.1%} EHP"`.
  - Flat stats as `"+25 Life"`, `"-12% Fire Res"`.
  - Each breached resist as the trade-off `"Fire Res turun di bawah cap (75% → 68%)"`.
  - Unmet requirements as `"Kebutuhan belum terpenuhi: Level 40/42"`.
  - Missing must-have mods as `"Prioritas guide kurang: <line>"`.

- [ ] **Step 1: Write the failing table test**

```python
@pytest.mark.parametrize("dps_b,dps_a,ehp_b,ehp_a,res_b,res_a,unmet,expected", [
    (1000, 1010, 500, 496, {}, {}, [], "EQUIP_NOW"),            # +1% DPS, -0.8% EHP
    (1000, 996, 500, 510, {}, {}, [], "EQUIP_NOW"),             # +2% EHP, -0.4% DPS
    (1000, 990, 500, 500, {}, {}, [], "REJECT"),                # -1% DPS, EHP flat
    (1000, 1005, 500, 500, {}, {}, [], "CONDITIONAL_UPGRADE"),  # below both bars
    (1000, 1000, 500, 500, {"fire": 75}, {"fire": 68}, [], "REJECT"),
    (1000, 1020, 500, 500, {"fire": 75}, {"fire": 68}, [], "CONDITIONAL_UPGRADE"),
    (1000, 1100, 500, 600, {}, {}, ["Level 40/42"], "REJECT"),
    (0, 5, 0, 0, {}, {}, [], "EQUIP_NOW"),                      # level-1 baseline: no ZeroDivisionError
])
def test_policy_table(dps_b, dps_a, ehp_b, ehp_a, res_b, res_a, unmet, expected):
    d = _delta(dps_b, dps_a, ehp_b, ehp_a, res_b, res_a)
    assert decide(d, unmet_requirements=unmet).verdict == expected

def test_must_have_caps_equip_now():
    sig = PrioritySignal(matched=1, total=2, must_have_missing=["25% increased Movement Speed"])
    assert decide(_delta(1000, 1100, 500, 600), priority=sig).verdict == "CONDITIONAL_UPGRADE"

def test_percent_labels():
    r = decide(_delta(1000, 1032, 500, 500))
    assert "+3.2% DPS" in r.gains
```
`_delta` builds a `PobEquipmentDelta(slot="Gloves", candidate_id=1, candidate_name="x", dps_before=…, dps_after=…, dps_delta=…, ehp_before=…, ehp_after=…, ehp_delta=…, res_before=…, res_after=…)`.

- [ ] **Step 2: Run** `uv run pytest tests/unit/equipment/test_policy.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(equipment): generic relative-threshold policy`

---

### Task 6: Tactical advisor as zone/resistance veto only

**Files:**
- Modify: `companion/equipment/tactical_advisor.py`
- Test: `tests/unit/equipment/test_tactical_advisor.py`; delete `tests/unit/equipment/test_tactical_map_hazards.py`

**Interfaces:**
- Produces:
  ```python
  def generate_tactical_advice(delta, candidate_raw: str = "", current_raw: str = "", zone_id: str | None = None,
                               character_level: int | None = None, base_verdict: Verdict | str = Verdict.CONDITIONAL_UPGRADE,
                               character_stats: Any = None) -> TacticalAdvice
  ```
- Verdict logic:
  - The verdict is `REJECT` only when one of two things holds:
    - the existing rule A (lethal zone resistance drop, the same condition as today);
    - an existing negative-resistance drop (cold, lightning, fire blocks).
  - Otherwise it equals `base_verdict`. The function never returns a verdict above `base_verdict`.
- Kept: sustain, attribute and requirement notes, zone texts and badges.
- Deleted:
  - The `fubgun_priorities` and `BuildProgressionStage` imports, and the `stage` parameter.
  - Rules B–I (absolute DPS/EHP thresholds and promotions).
  - Every "Fubgun"/"granat" text.
  - `evaluate_tactical_map_hazards`: dead code (no caller), Fubgun-specific.
- `merge_verdicts` is unchanged.

- [ ] **Step 1: Write the failing tests** (add to `test_tactical_advisor.py`):

```python
def test_tactical_never_promotes():
    adv = generate_tactical_advice(_clean_upgrade_delta(), zone_id="G1_1", base_verdict="CONDITIONAL_UPGRADE")
    assert adv.verdict == Verdict.CONDITIONAL_UPGRADE

def test_tactical_vetoes_lethal_zone_drop():   # reuse the Kraken Dome / G2_1 fire-drop case already in this file
    assert _kraken_case(base_verdict="EQUIP_NOW").verdict == Verdict.REJECT

def test_tactical_text_has_no_fubgun():
    adv = generate_tactical_advice(_clean_upgrade_delta(), base_verdict="EQUIP_NOW")
    assert "fubgun" not in adv.model_dump_json().lower()
```
Existing tests that pin rules B–I or a promotion (weapon DPS loss, boots MS, attribute drain, triple negative, offensive slot, decisive EQUIP_NOW cases) are deleted. Tests of rule A, negative resistances and unmet requirements are kept and updated to the new signature. List every deleted test in the report.

- [ ] **Step 2: Run** `uv run pytest tests/unit/equipment/test_tactical_advisor.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.** `dashboard_api` still calls the old signature until Task 8. Update its two call sites now: drop `stage=` and pass `base_verdict=rec.verdict`, so the suite stays green.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `refactor(tactical): zone/resistance veto only; drop Fubgun policy and promotions`

---

### Task 7: `evaluation.evaluate`

**Files:**
- Create: `companion/equipment/evaluation.py`, `companion/equipment/current_item.py`
- Modify: `companion/dashboard_api.py` (move `get_current_raw`, `get_current_item_info` and `character_level_and_zone` to `current_item.py` and re-import them under the same names, because `dashboard_server.py` and the tests import them from `dashboard_api`)
- Test: `tests/unit/equipment/test_evaluation.py`

**Interfaces:**
- Consumes: Tasks 1–6, `builds.store.get_assignment/load_guide`, `builds.stages.resolve_stage`, `parse_item_text`, `partial_projection.project_candidate_on_loadout`, `loadout_cli.load_loadout`, `baseline_cli.load_baseline`, `zone_threats`.
- Produces:
  ```python
  class GuideSignal(BaseModel):
      name: str; stage_title: str
      priority_match: float | None = None
      must_have_missing: list[str] = []
      target_fit: dict[str, float] | None = None       # Phase 4
  class EvaluationResult(BaseModel):                   # fields exactly as spec §5
      verdict: str; engine: str; engine_reason: str | None = None
      slot: str; slot_reason: str
      per_slot: list[SlotResult]
      dims: dict[str, float] = {}
      guide: GuideSignal | None = None
      safety: list[str] = []
      reasons: list[str] = []; trade_offs: list[str] = []; gains: list[str] = []
      tactical_advice: dict | None = None
      current_item_name: str | None = None
      item_name: str; base_type: str
  def evaluate(raw_text: str, character_id: str, *, runtime_dir: Path, pob_session: Any | None,
               source: Literal["manual", "auto", "cli"], locked_slot: str | None = None,
               zone: str | None = None, stage_override: str | None = None) -> EvaluationResult
      # raises ValueError (Indonesian message) for unparseable / non-equippable items or a bad locked slot
  ```
- Order, following spec §5:
  1. **Context.**
     - Parse the candidate.
     - The effective level is `max(file level, pob_session.level)`. The zone is `zone or file zone`.
     - Read the assignment. `stage_override` wins over the stored override.
     - When `load_guide` returns `None`, use character-only mode: `profile=None` and the stage is `GuideStage(id="all", title="Karakter saja")`.
  2. **Slots.** Call `resolve_slots`.
  3. **Safety.**
     - When `weapon_not_in_guide` returns a reason, return REJECT for all plans.
     - Otherwise each plan with `breaker_reasons` becomes `rejected(slot, reasons)`.
     - The engine is never called for vetoed slots.
  4. **Already equipped.** When a plan slot's current item parses to the same `(name, base_type)` and the candidate rarity is rare or unique, return `ALREADY_EQUIPPED` for that slot.
  5. **Measure.**
     - **PoB2 path.** Use it when `pob_session` is available: submit one candidate per evaluation (`source=source`), then `measure(slot, raw, cid, source=source, clear_slots=plan.clear_slots)`.
     - **Fallback.** A `None` result or an exception (logged) switches every remaining slot to the heuristic, with `engine_reason="PoB2 tidak memberi hasil; memakai estimasi"`.
     - **Heuristic, weapons:** `insufficient(slot, "Tanpa PoB2 senjata tidak bisa dinilai")`.
     - **Heuristic, other slots:** build a `PobEquipmentDelta` from `project_candidate_on_loadout`.
       - `life` delta and before come from `projected_absolute - delta`.
       - `ehp` equals life.
       - `res_before`/`res_after` are filled when `is_absolute_known`.
       - `dps_before = dps_after = 0`.
       - Unknown life before gives `insufficient(slot, "Life baseline belum diketahui")`.
  6. **Policy.**
     - Call `decide(...)` with `unmet_requirements` from `candidate.required_level/str/dex/int` against the effective level and the baseline attributes.
     - Pass `priority=priority_signal(stage.items.get(slot), candidate mod lines)`.
     - Pass `is_empty` from `pob_session.is_slot_empty(slot)`, or from `get_current_raw(...) == ""` on the heuristic path.
  7. **Choice.**
     - An empty slot with a non-REJECT verdict wins.
     - Otherwise the highest `VERDICT_RANK` wins, with ties broken by `dps_pct` then `ehp_pct`.
     - All results go to `per_slot`.
  8. **Tactical.** Call `generate_tactical_advice(chosen.delta, raw, current_raw(chosen slot), zone, level, base_verdict=chosen.verdict, character_stats)`. The final verdict is `merge_verdicts(chosen.verdict, tactical.verdict)`. Skip this step when `chosen.delta` is `None`.
- `dims` holds:
  - `dps_pct` and `ehp_pct`;
  - the chosen delta's `life`, `armour`, `evasion`, `energy_shield`, `fire_res`, `cold_res`, `lightning_res`, `chaos_res` and `movement_speed` deltas.

- [ ] **Step 1: Write the failing tests.** Each test installs guides from `tests/fixtures/guides/` into `tmp_path` with `import_guide_payload`, writes `characters/<id>.json` with a level, and calls `set_assignment`. The PoB2 tests use a stub session exposing `is_available`, `level`, `submit_candidate`, `measure`, `is_slot_empty` and `get_equipped_item`.

```python
def test_audit_probe_rejected_on_both_engines(tmp_path, positive_pob_stub):
    _install(tmp_path, "fubgun-flameblast-oil-grenade", char="BOMSHAK", level=53)
    for sess in (positive_pob_stub, None):
        r = evaluate(PROBE_GLOVES, "BOMSHAK", runtime_dir=tmp_path, pob_session=sess, source="manual")
        assert r.verdict == "REJECT" and "Oil Grenade" in r.safety[0]

def test_same_probe_not_vetoed_with_navira(tmp_path, positive_pob_stub):
    _install(tmp_path, "naviras-fracturing-varashta-league-starter", char="SORC", level=53)
    r = evaluate(PROBE_GLOVES, "SORC", runtime_dir=tmp_path, pob_session=positive_pob_stub, source="manual")
    assert r.safety == [] and r.verdict == "EQUIP_NOW"

def test_manual_and_auto_identical(tmp_path, positive_pob_stub):
    _install(tmp_path, "fubgun-flameblast-oil-grenade", char="BOMSHAK", level=60)
    a = evaluate(RING_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=positive_pob_stub, source="manual")
    b = evaluate(RING_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=positive_pob_stub, source="auto")
    assert a.model_dump() == b.model_dump()

def test_tactical_cannot_promote(tmp_path, flat_pob_stub):          # policy CONDITIONAL, clean zone
    _install(tmp_path, "fubgun-flameblast-oil-grenade", char="BOMSHAK", level=60)
    assert evaluate(BOOTS_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=flat_pob_stub, source="manual").verdict == "CONDITIONAL_UPGRADE"

def test_character_only_mode_when_no_guide(tmp_path, positive_pob_stub):
    _write_char(tmp_path, "X", level=30)
    r = evaluate(BOOTS_TEXT, "X", runtime_dir=tmp_path, pob_session=positive_pob_stub, source="manual")
    assert r.guide is None and r.verdict == "EQUIP_NOW"

def test_pob_failure_falls_back_with_reason(tmp_path, failing_pob_stub):
    _install(tmp_path, "fubgun-flameblast-oil-grenade", char="BOMSHAK", level=60)
    r = evaluate(BOOTS_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=failing_pob_stub, source="manual")
    assert r.engine == "heuristic" and r.engine_reason

def test_heuristic_weapon_is_insufficient(tmp_path):
    _install(tmp_path, "fubgun-flameblast-oil-grenade", char="BOMSHAK", level=60)
    assert evaluate(CROSSBOW_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=None, source="manual").verdict == "INSUFFICIENT_DATA"

def test_empty_ring_slot_wins(tmp_path, ring2_empty_stub):
    _install(tmp_path, "fubgun-flameblast-oil-grenade", char="BOMSHAK", level=60)
    assert evaluate(RING_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=ring2_empty_stub, source="auto").slot == "Ring 2"

def test_guide_signal_reports_stage_and_priority(tmp_path, positive_pob_stub):
    _install(tmp_path, "fubgun-flameblast-oil-grenade", char="BOMSHAK", level=20)
    r = evaluate(BOOTS_TEXT, "BOMSHAK", runtime_dir=tmp_path, pob_session=positive_pob_stub, source="manual")
    assert r.guide.stage_title == "lvl 15-32" and r.guide.priority_match is not None
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/equipment/test_evaluation.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(equipment): single guide-aware evaluation pipeline`

---

### Task 8: Dashboard on `evaluation.evaluate`; delete the Fubgun branches

**Files:**
- Modify: `companion/dashboard_api.py`, `companion/dashboard_server.py` (only if it passes legacy args)
- Test: `tests/unit/test_dashboard_api.py`, `tests/unit/equipment/test_compare_item_accuracy.py`, `tests/unit/equipment/test_verdict_merge.py`, `tests/api/test_pob2_and_cli.py`, `tests/test_m10_integration.py`

**Interfaces:**
- Consumes: `evaluate`, `EvaluationResult`, `UI_SLOT_KEYS`.
- Produces:
  - `evaluate_item_payload(payload, runtime_dir, pob_session=None) -> dict`:
    - Calls `evaluate(payload["raw_text"], resolve_char_id(...), runtime_dir=…, pob_session=…, source=payload.get("source", "manual"), locked_slot=payload.get("slot") or None, zone=payload.get("zone"))`.
    - A `ValueError` becomes `{"error": str(exc)}`.
    - Empty text keeps `{"error": "Item raw text is empty."}`.
  - `check_auto_clipboard` passes `source="auto"`. Its dedupe key is unchanged.
  - `flatten_result(r: EvaluationResult) -> dict`. Keys:
    - From the old response: `success=True`, `engine`, `item_name`, `base_type`, `verdict`, `reason`, `gains`, `trade_offs`, `formatted_report`, `tactical_advice`, `current_item_name`, `current_item_base_type`, `is_weapon`, `dps_delta`, `life_delta`.
    - `slot` is `UI_SLOT_KEYS[r.slot]`.
    - `reason` is `r.reasons[0]`, else the tactical headline, else the verdict.
    - `formatted_report` is a short text block: verdict, slot, reasons, gains, trade-offs.
    - `dps_delta` and `life_delta` are absolute values from the chosen delta.
    - New keys: `pob_slot=r.slot`, `recommended_slot=r.slot`, `slot_reason`, `engine_reason`, `dims`, `guide`, `safety`, `per_slot` (dumped).
- Deleted from `dashboard_api`:
  - `_STAGE_MAP`, `_resolve_stage`, `_SLOT_DISPLAY`, `_EvalContext`, `_build_eval_context`, `_zone_reject_report`, `_incompatible_weapon`;
  - every `_pob2_*` function, `_known_delta`, `_evaluate_heuristic`;
  - imports of `EquipmentIntelligenceEngine`, `fubgun_priorities`, `live_watcher.evaluate_live_candidate` and `BuildProgressionStage` that become unused.

- [ ] **Step 1: Migrate the tests first.** Go through every evaluate/compare test in the listed files.
  - **Keep and rewrite** tests of behaviour the spec keeps, against `evaluate_item_payload` with an installed guide and a stub session:
    - success shape;
    - requested slot respected;
    - Set 2 routing;
    - off-hand to `Weapon 2`;
    - dual-ring choice;
    - zone-aware tactical advice present;
    - auto-clipboard zone and context re-evaluation;
    - `evaluated_at` stamp;
    - PoB2 failure engine tag;
    - real current item name;
    - empty and malformed input.
  - **Delete** tests that assert Fubgun policy text, Navira or `generic_pob2` guide ids, or the deleted internals. Examples: `test_generic_pob2_weapon_verdicts`, `test_evaluate_item_payload_navira_varashta_*`, and the `generic_pob2` weapon test. Replace their intent with one test each:
    - a weapon class absent from the assigned guide gives REJECT with "Senjata tidak dipakai guide";
    - a weapon present in the guide is measured.
  - List every deleted test with a one-line reason in the report.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_dashboard_api.py tests/unit/equipment tests/api -q`. Expected: the rewritten tests FAIL against the old implementation.
- [ ] **Step 3: Implement** the interfaces above.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS. Also run `uv run python -c "import companion.dashboard_api as m; assert not hasattr(m, '_STAGE_MAP')"`.
- [ ] **Step 5: Commit** `refactor(dashboard): evaluate through evaluation.evaluate; remove Fubgun branches`

---

### Task 9: Sidebar guide and stage from stored guides; bookmarklet comments

**Files:**
- Modify: `dashboard/js/controls.js`, `dashboard/index.html` (sidebar `guide-select` / `stage-select` options), `dashboard/js/compare.js` (stop sending `guide`/`stage`), `dashboard/bookmarklet.js` (M9)
- Test: `tests/unit/builds/test_guide_fixtures.py` (bookmarklet has no `//` line comments)

**Interfaces:**
- Consumes:
  - `GET /api/guides?char_id=<id>` returns `{guides:[{slug,name,stages:[{id,title,auto}]}], active:{guide, stage_override}}`.
  - `POST /api/character-guide` takes `{character_id, guide, stage_override}` (Phase 1).
- Behaviour:
  - **Guide dropdown.** Options are `"Karakter saja"` (value `""`) plus every guide name (value = slug). The active guide comes from `active.guide`.
    - On change, POST `{character_id, guide: value || null, stage_override: null}`.
    - Then rebuild the stage dropdown.
  - **Stage dropdown.** Options are `"Auto (berdasarkan level)"` (value `""`) plus every stage title (value = id). The selected stage is `active.stage_override`.
    - On change, POST `{character_id, guide, stage_override: value || null}`.
  - **Character switch.** Re-fetch `/api/guides?char_id=…` and select the stored assignment. Delete the class-based auto-guide logic.
  - **Deleted:** `GUIDE_STAGES_MAP`, `refreshStageDropdown`'s hardcoded lists, and the hardcoded `<option>`s in `index.html`.
  - **Error feedback.** A failed POST shows the server `error` in `guide-status-note`.
  - **Bookmarklet.** `bookmarklet.js` uses only `/* */` comments.

- [ ] **Step 1: Write the failing test**

```python
def test_bookmarklet_has_no_line_comments():
    src = Path("dashboard/bookmarklet.js").read_text(encoding="utf-8")
    assert not re.search(r"(^|\s)//", src, re.M)
```
- [ ] **Step 2: Run** `uv run pytest tests/unit/builds/test_guide_fixtures.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the JS/HTML changes and convert the bookmarklet comments.
- [ ] **Step 4: Verify.**
  - Run `uv run pytest -q`. Expected: PASS.
  - Start the dashboard (`uv run python -m companion.dashboard_server`, or the project's usual launch) and open it in the browser pane. Check these:
    - The guide dropdown lists the three stored guides and "Karakter saja".
    - Choosing Fubgun shows its 9 stage titles.
    - The choice survives a page reload.
    - Pasting a ring into compare returns a verdict with no console errors.
- [ ] **Step 5: Commit** `feat(dashboard): sidebar guide/stage from stored guides; bookmarklet block comments`

---

### Live check (controller, after Task 9)

Spec §10 asks for these checks with the PoB2 engine running:
- one real Set 2 crossbow comparison;
- one ring comparison.

Record the verdict, `slot`, `dps_pct` and `engine` of each in the ledger. If Docker or the OAuth token is unavailable, record `skipped: <reason>`. Thresholds are calibrated after this check, in a later plan.
