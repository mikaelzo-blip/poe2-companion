# Phase 4: Guide-Build Simulation, CLI on the Pipeline, Fubgun Retirement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the multi-guide redesign:
- the verdict card shows how a candidate fits the guide's own PoB build ("Di build target");
- the CLI uses the same `evaluation.evaluate` pipeline as the dashboard;
- the Fubgun-only modules, their tests and the "Lvl 52 Transition" tab are deleted.

**Architecture:**
- `Pob2EquipmentSession.measure` gains `base_xml`, which measures against any XML (the guide's) instead of the character's. Step 7 of `evaluate` uses it once, informationally, for the chosen slot.
- The CLI commands `gear live`, `gear inspect-clipboard` and `gear evaluate` become thin loops over `evaluate(..., source="cli")`, printing `dashboard_api.flatten_result`.
- Once nothing imports the legacy chain (`live_watcher` → `engine` → `fubgun_*` / `build_breaker*` / `pob2_helmet_advisor`), it is deleted together with its tests.

**Tech Stack:** Python 3 / pydantic / pytest; plain ES-module JS; Playwright e2e harness in `tests/e2e/`.

**Spec:** `docs/superpowers/specs/2026-10-10-multi-guide-evaluation-design.md`:
- §5 step 7 (guide-build simulation);
- §10 (migration);
- §11 (phase 4 scope).

It also takes these carry-overs:
- `pob_stage_id` (M7) from `.superpowers/sdd/2026-10-10-phase1-guide-model/final-review.md`;
- the "leave for Phase 4" rows in `.superpowers/sdd/2026-10-11-phase2-evaluation-pipeline/final-review.md`;
- the Phase 3 ledger minors in `.superpowers/sdd/2026-10-11-phase3-dashboard-ui/progress.md`.

## Global Constraints

- Personal single-user local tool: no LAN, auth or multi-user work.
- Never fetch mobalytics server-side.
- UI and CLI copy is Indonesian, matching the existing strings. Code identifiers stay English.
- Every server string inserted into HTML goes through `esc()`.
- Policy thresholds, `safety.py` rules and the verdict logic of `evaluate` are unchanged. Guide-build simulation is informational only and never changes `verdict`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never create files in the repo root via shell redirects.
- Full suite `uv run pytest -q` is green at the end of every task (baseline 2167). `uv run pytest tests/e2e -q` is green when the task touches `dashboard/`.
- Deleting a test file is allowed only in Task 4. Each deletion is listed in that task's report with the behaviour it pinned and the surviving test that covers it, or "internal only".

## Review Focus

1. **Missing guide XML.** The guide has `has_pob: true` but the `.xml` is missing or unreadable on disk. Expected: `target_fit` is None, the verdict is unchanged, and a warning is logged. Pinned in Task 2, `test_target_fit_none_when_guide_xml_missing`.
2. **Guide measurement fails.** The guide measurement returns None or raises. Expected: the verdict and `per_slot` are identical to the run without it. Pinned in Task 2, `test_target_fit_failure_keeps_verdict`.
3. **Not the PoB stage.** The active stage is not the guide's `pob_stage_id`. Expected: no second `measure` call. Pinned in Task 2, `test_no_guide_measure_off_pob_stage`.
4. **Clipboard noise in `gear live`.** The same clipboard text twice is evaluated once, non-item text is ignored, and a parse error prints one line and the loop continues. Pinned in Task 3, `test_live_dedupes_and_skips_noise`.
5. **CLI without PoB2.** The CLI runs with PoB2 unavailable. Expected: the heuristic result is printed with `engine_reason`, and the exit code is 0. Pinned in Task 3, `test_cli_evaluate_heuristic_prints_engine_reason`.

---

### Task 1: `pob_stage_id` matches the guide XML's active item set (M7)

**Files:**
- Modify: `companion/dashboard_api.py` `import_guide_payload` (~line 760-800, where the mobalytics PoB code is decoded)
- Modify or create: a helper `active_item_set_title(xml: str) -> str | None` in `companion/builds/pob_code.py`
- Test: `tests/unit/builds/test_pob_code.py`, `tests/unit/builds/test_guide_api.py`

**Interfaces:**
- Produces:
  - `active_item_set_title(xml: str) -> str | None`. It returns the `title` of the `<ItemSet>` whose `id` equals `<Items activeItemSet=...>`, or None.
  - After a mobalytics import with decodable XML, `profile.pob_stage_id` is the id of the first stage whose title equals that set title (case-insensitive, whitespace-trimmed). If nothing matches, it stays the last stage, as today.

- [ ] **Step 1: Write failing tests**
  - `test_active_item_set_title`: a minimal XML with two `<ItemSet id="1" title="Leveling">` / `<ItemSet id="2" title="Late Endgame">` and `<Items activeItemSet="2">` gives `"Late Endgame"`. Missing attribute gives None.
  - `test_mobalytics_import_pob_stage_matches_active_set`: import the Navira fixture (`tests/fixtures/guides/naviras-fracturing-varashta-league-starter.json`) into `tmp_path`. `load_guide(...).pob_stage_id` is the id of the stage titled like the XML's active set (`"Late Endgame"`), not the last stage.
- [ ] **Step 2: Run** `uv run pytest tests/unit/builds -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the helper and the override in `import_guide_payload`.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `fix(builds): pob_stage_id follows the guide XML active item set`

### Task 2: Guide-build simulation (`target_fit`)

**Files:**
- Modify: `companion/equipment/pob2_equipment_advisor.py` `measure` (~line 846)
- Modify: `companion/equipment/evaluation.py`. Add a step-7 block after the chosen slot is known; `GuideSignal.target_fit` already exists.
- Modify: `dashboard/js/compare.js`. Drop the speculative `target_fit` alias keys (`data.target_fit`, `tf.dps`, `tf.ehp`); read only `data.guide.target_fit.dps_pct` / `.ehp_pct`.
- Test: `tests/unit/equipment/test_evaluation.py`, `tests/unit/equipment/test_pob2_equipment_advisor.py`, `tests/e2e/test_verdict_card.py`

**Interfaces:**
- Consumes:
  - `load_guide_xml(runtime_dir, slug) -> str | None` from `companion/builds/store.py`;
  - `GuideProfile.has_pob` and `GuideProfile.pob_stage_id`.
- Produces:
  - `measure(slot, raw, candidate_id, *, source="manual", clear_slots=(), candidate_name="", base_xml: str | None = None)`. When `base_xml` is given:
    - it is used instead of `self.xml` for both readings;
    - the main skill is NOT locked, because the guide XML carries its own main skill;
    - the sandbox is still restored to `self.xml` in `finally`.
  - `GuideSignal.target_fit = {"dps_pct": float, "ehp_pct": float}`, computed only when all of these hold:
    - the guide `has_pob`;
    - the resolved stage id equals `profile.pob_stage_id`;
    - PoB2 is available and the chosen slot was measured with pob2;
    - the verdict is not REJECT or ALREADY_EQUIPPED.

    In every other case it is None. A None result or an exception from the guide measure is logged (warning) and leaves `target_fit` None.

- [ ] **Step 1: Write failing tests**
  - In `test_pob2_equipment_advisor.py`, use the existing mock-engine fixtures. `test_measure_base_xml_uses_guide_xml_and_restores`:
    - the first `import_build` call carries the guide XML (after the weapon-set rewrite);
    - no `set_main_skill` call is made;
    - the last `import_build` call carries `session.xml`.
  - In `test_evaluation.py`, extend the `Stub` in `tests/unit/conftest.py` so `measure` records `base_xml` and returns a different delta for it, for example +10% DPS. Write the guide XML with `save_guide(..., pob_xml=...)`.
    - `test_target_fit_on_pob_stage`: on the guide's PoB stage (via `stage_override`), `r.guide.target_fit == {"dps_pct": pytest.approx(0.10), "ehp_pct": ...}`, and `r.verdict` equals the verdict of the same run without guide XML.
    - `test_no_guide_measure_off_pob_stage`: on another stage, no call has `base_xml` set and `target_fit is None`.
    - `test_target_fit_none_when_guide_xml_missing`: `has_pob` is true and the `.xml` is deleted. `target_fit is None` and the verdict is unchanged.
    - `test_target_fit_failure_keeps_verdict`: the stub returns None, or raises, for `base_xml` calls. `target_fit is None`, and the verdict and `per_slot` are unchanged.
  - In `tests/e2e/test_verdict_card.py`, update `test_card_target_fit_and_heuristic_engine_reason` to use only `guide.target_fit.{dps_pct, ehp_pct}`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/equipment/test_evaluation.py tests/unit/equipment/test_pob2_equipment_advisor.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** as in Interfaces. Pass the chosen plan's `clear_slots` to the guide measure too.
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run pytest tests/e2e -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat(evaluation): guide-build simulation fills target_fit on the guide's PoB stage`

### Task 3: CLI `gear live` / `inspect-clipboard` / `evaluate` on the pipeline

**Files:**
- Create: `companion/equipment/cli_eval.py`. It is the only home for the new CLI logic.
- Modify: `companion/cli.py`:
  - the `handle_gear_live`, `handle_gear_inspect_clipboard` and `handle_gear_evaluate` handlers (~line 1174-1240);
  - the `gear live` / `inspect-clipboard` / `evaluate` parser options (~line 270-297).
- Test: create `tests/unit/equipment/test_cli_eval.py`

**Interfaces:**
- Consumes: `evaluate` and `flatten_result` (from `companion.dashboard_api`), `get_clipboard_text`, and `Pob2EquipmentSession(character_name=...)` with `.initialize()`.
- Produces in `cli_eval.py`:
  - `format_result(res: dict) -> str`. It renders the human text below from a `flatten_result` dict.
  - `evaluate_once(raw: str, runtime_dir: Path, character_id: str, *, pob_session, locked_slot: str | None = None, stage_override: str | None = None, as_json: bool = False) -> tuple[int, str]`. It returns (exit code, output text). On `ValueError` it returns exit code 1 with the message.
  - `run_live(runtime_dir: Path, character_id: str, *, pob_session, poll_interval: float = 0.25, as_json: bool = False, clipboard_reader: Callable[[], str] = get_clipboard_text, output_writer: Callable[[str], None] = print, max_polls: int | None = None) -> int`:
    - dedupes on clipboard text;
    - ignores text without `Rarity:` / `Item Class:`;
    - on `ValueError` writes `Item dilewati: <message>`;
    - returns 0 on KeyboardInterrupt or when `max_polls` is reached.
  - `open_pob_session(character_id: str, enabled: bool) -> Pob2EquipmentSession | None`. It returns None when disabled or when `initialize()` fails, and when it fails it prints `PoB2 tidak tersedia: <unavailable_reason>`.
- CLI options:
  - `gear live`: `--json`, `--poll-interval`, `--no-pob`, `--pob-character`, `--stage` (passed as `stage_override`; it accepts a guide stage id or title).
  - `gear inspect-clipboard` and `gear evaluate <file>`: the same, plus `--slot` (passed as `locked_slot`, canonical names like "Ring 1").
  - Removed: `--bootstrap`, `--weapon-set`, and the old `BuildProgressionStage` choices for `--stage`.
- Human text format, one block per item:

  ```
  <VERDICT> — <item_name> → <slot label as pob_slot> (<slot_reason>)
    DPS +1.2% · EHP −0.4%          (omitted for INSUFFICIENT_DATA / ALREADY_EQUIPPED / engine none)
    ⛔ <safety reason>              (one line each)
    + <gain> / - <trade-off>        (one line each)
    Guide: <name> · <stage_title> · Prioritas <m>/<t>   (omitted without guide)
    Engine: heuristik — <engine_reason>                 (only when engine != pob2)
  ```

  With `--json`, one `json.dumps(flatten_result(...))` per line.

- [ ] **Step 1: Write failing tests** in `test_cli_eval.py`. Reuse the helpers in `tests/unit/conftest.py` (`_install`, `_item`, the `Stub` sessions).
  - `test_format_result_lines`:
    - an EQUIP_NOW flatten dict with `dps_pct: 0.0123`, `ehp_pct: -0.004`, one gain and one safety reason contains `DPS +1.2% · EHP −0.4%`, `⛔ `, `+ ` and the slot reason;
    - an INSUFFICIENT_DATA dict has no `DPS ` line.
  - `test_cli_evaluate_heuristic_prints_engine_reason`: `evaluate_once` with `pob_session=None` on a boots item gives exit code 0 and output containing `Engine: heuristik`.
  - `test_evaluate_once_value_error_exit_1`: a currency item (`Item Class: Stackable Currency`) gives exit code 1 with the slot error message.
  - `test_live_dedupes_and_skips_noise`:
    - the reader yields `[boots, boots, "hello", currency, ring]` and then repeats `ring`, with `max_polls=6`;
    - the writer receives exactly 2 result blocks (boots, ring) and one `Item dilewati:` line;
    - the return code is 0.
  - `test_live_json_one_line_per_item`: with `as_json=True`, each written line parses with `json.loads` and has a `verdict` key.
  - `test_cli_parser_gear_live_options`: parsing `gear live --no-pob --stage 3` succeeds, and `gear live --bootstrap` exits with an argparse error.
- [ ] **Step 2: Run** `uv run pytest tests/unit/equipment/test_cli_eval.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `cli_eval.py` and rewire the three handlers in `cli.py`. Do not delete `live_watcher.py` yet; Task 4 does that.
- [ ] **Step 4: Run** `uv run pytest -q`. Old tests that drive the removed CLI flags may fail. List them in the report; do not delete them here. Task 4 decides.
- [ ] **Step 5: Commit** `feat(cli): gear live/inspect-clipboard/evaluate use the evaluation pipeline`

### Task 4: Retire the Fubgun chain and its tests

**Files:**
- Delete:
  - `companion/equipment/live_watcher.py`
  - `companion/equipment/engine.py`
  - `companion/equipment/fubgun_priorities.py`
  - `companion/equipment/fubgun_rules.py`
  - `companion/equipment/fubgun_weapon_router.py`
  - `companion/equipment/build_breaker.py`
  - `companion/equipment/build_breaker_gate.py`
  - `companion/equipment/pob2_helmet_advisor.py`
- Modify:
  - `companion/equipment/clipboard.py`: delete `run_inspect_clipboard`, `run_evaluate_file` and the `engine` import.
  - `companion/equipment/data_sufficiency.py`: remove the `is_fubgun_non_material_modifier` hook (~line 70). The function keeps only the generic regex.
  - `companion/equipment/pob2_equipment_advisor.py`: delete the wrappers whose only caller was `live_watcher` (`simulate_ring_candidate`, the ambiguous-1H wrapper and `simulate_item` if unused after the grep), plus the dead `"EngineError" in type(exc).__name__` branch in `measure`.
  - `companion/dashboard_api.py` `_update_character_stats_payload_locked`: drop `infer_stage_from_level` and the `display_map`. Set `build_progression.active_stage` from the character's guide assignment through `companion.builds.stages.resolve_stage(profile, level, override)` (the same resolution `evaluation._resolve_guide` uses): the resolved stage title for the level, or "Karakter saja" when no guide is assigned.
- Delete tests: every test file under `tests/` that imports a deleted module or symbol (find with grep). Before deleting each file, check whether it pins user-visible behaviour that `evaluate` must keep, such as the fire-to-attacks REJECT or Set 2 crossbow routing:
  - if a surviving test already covers it (`tests/unit/equipment/test_evaluation.py`, `test_safety.py`, `test_slot_resolver.py`, `test_policy.py`), name it in the report;
  - if not, add the missing case to `test_evaluation.py` before deleting.
- Test: `tests/unit/test_dashboard_api.py` (stage display)

**Interfaces:**
- Consumes: Task 3's CLI, so nothing in `companion/` imports `live_watcher` any more.
- Produces: no new API.

- [ ] **Step 1: Write the failing test** `test_update_stats_stage_from_guide`:
  - BOMSHAK is assigned the Fubgun fixture guide (`_install`), and a level 37 stats update makes `active_stage` the Fubgun auto stage title for level 37;
  - with no assignment, it is `"Karakter saja"`.
- [ ] **Step 2: Run** it. Expected: FAIL.
- [ ] **Step 3: Delete and edit** as listed. Then run `uv run python -c "import companion.cli, companion.dashboard_server"` and a grep for each deleted module name under `companion/` and `tests/`. Both must come back clean.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass. The test count drops; report before/after counts and the deletion table.
- [ ] **Step 5: Commit** `refactor: retire Fubgun-specific modules, legacy watcher and their tests`

### Task 5: Remove the "Lvl 52 Transition" tab

**Files:**
- Modify: `dashboard/index.html`. Remove the nav item `data-tab="tab-transition"` (~line 103-109) and the `<section id="tab-transition">` (~line 493-530).
- Modify: `dashboard/js/overview.js` (the `transition-*` element writes, ~line 95) and any other JS that touches `transition-*` ids (grep).
- Modify: `dashboard/style.css`. Remove `.transition-*` / `.readiness-*` / `.req-*` rules only if no remaining element uses them (grep `index.html` first).
- Test: `tests/e2e/test_dashboard_shell.py` (create)

- [ ] **Step 1: Write the failing e2e test** `test_no_transition_tab_and_no_console_errors`. After load:
  - `.nav-item[data-tab="tab-transition"]` count is 0, and `#tab-transition` count is 0;
  - clicking every remaining `.nav-item` raises no console error. Collect them with `page.on("console")` filtered to `error`, plus `page.on("pageerror")`.
- [ ] **Step 2: Run** it. Expected: FAIL.
- [ ] **Step 3: Remove** the tab, its JS and the unused CSS.
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run pytest tests/e2e -q`. Expected: all pass.
- [ ] **Step 5: Commit** `refactor(dashboard): remove Fubgun Lvl 52 Transition tab`

### Task 6: Carry-over cleanups

**Files:**
- Create: `tests/unit/eval_helpers.py`. Move the helper functions and classes (`_install`, `_item`, `_write_char`, `Stub`, `Flat`, `Failing`, `Ring2Empty`, `FIX`, `FUB`) out of `tests/unit/conftest.py`. The conftest keeps only the fixtures. Update every `from tests.unit.conftest import` to `from tests.unit.eval_helpers import`.
- Modify: `companion/equipment/tactical_advisor.py`. Delete `_extract_flat_attack_damage` and `_extract_sustain` if grep confirms they are unused.
- Modify: `companion/equipment/current_item.py`. Fold the duplicated loadout lookup (`get_current_raw` and `get_current_item_info` both load and resolve the loadout) into one private helper `_loadout_item(runtime_dir, char_id, slot_name)`.
- Test: `tests/unit/equipment/test_pob2_equipment_advisor.py`. These are the lifecycle tests the Phase 2 review left for Phase 4.

- [ ] **Step 1: Write the failing or pinning tests** in `test_pob2_equipment_advisor.py` with the mock engine:
  - `test_measure_superseded_mid_measure_returns_none`: `is_stale` flips to True between the before and after readings, so `measure` returns None and the baseline is restored.
  - `test_measure_engine_error_marks_unhealthy`: the mock raises `EngineError` on `equip_item`, giving `session.is_healthy is False` and an `unhealthy_reason` that starts with `"Engine error:"`.
- [ ] **Step 2: Run** them. Expected: PASS or FAIL. They are regression pins; any failure is a real bug to fix in this task.
- [ ] **Step 3: Implement** the moves, deletions and the helper.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass. The test count is unchanged apart from the two new tests.
- [ ] **Step 5: Commit** `refactor: test helpers module, drop dead tactical extractors, single loadout lookup`

### End-of-phase check (controller)

- **Browser pane, real dashboard.** The Lvl 52 tab is gone and every tab opens without console errors. A ring compare still shows the server slot.
- **Guide-build fit.** If PoB2 is available (Docker running, fresh GGG token), compare one item on the Navira guide with the stage override set to its PoB stage. The card shows "Di build target: …". Otherwise record "skipped: PoB2 unavailable" in the ledger.
- **CLI.** `uv run python -m companion.cli gear evaluate <file with a boots item> --no-pob` prints a result block with exit code 0.
- **Cleanup.** Restore any assignment or stage override changed during the check.
