# Phase 3: Dashboard UI for Multi-Guide Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard trust the server's evaluation. Manual and auto-scan compares use the slot the server picked. Auto-equip runs only on `EQUIP_NOW` into a slot the server reports empty. The verdict card shows the guide signals. The guide tab gets a breaker-rule editor.

**Architecture:**
- Decisions move server-side wherever a Python test can pin them. `flatten_result` gains `dps_pct`, `ehp_pct`, `slot_empty`, `auto_equip_ok` and guide priority counts.
- The JS only reads those fields.
- The JS gets its first test harness: Playwright (already a dev dependency) driving the static `dashboard/` files, with every `/api/*` call mocked by `page.route`.

**Tech Stack:** Python 3 / pydantic / pytest; plain ES-module JS (no build step); Playwright for Python (bundled Chromium cached in `%LOCALAPPDATA%\ms-playwright`).

**Spec:** `docs/superpowers/specs/2026-10-10-multi-guide-evaluation-design.md`. This plan covers §8 (UI) and audit findings #5 (UI part), #11 and #18 from `docs/audits/2026-10-10-COMPARE_AND_MCP_IMPORT_AUDIT.md`. It also takes the carry-overs marked "Phase 3" in `.superpowers/sdd/2026-10-11-phase2-evaluation-pipeline/final-review.md`.

## Global Constraints

- Personal single-user local tool: no LAN, auth or multi-user work.
- Never fetch mobalytics server-side; guides come in only through the user-run bookmarklet.
- UI copy is Indonesian, matching the existing dashboard strings.
- Every server-provided string inserted into HTML goes through `esc()` from `dashboard/js/state.js`.
- No new JS dependencies and no JS build step.
- Policy thresholds (`companion/equipment/policy.py` constants) are unchanged.
- Legacy Fubgun modules, the "Lvl 52 Transition" tab and the CLI `live_watcher` are untouched (Phase 4).
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never create files in the repo root via shell redirects (`> int`, `-> X`). Write scratch files only under the test `tmp_path`.
- Full suite `uv run pytest -q` is green at the end of every task. The baseline is 2138 passed.

## Review Focus

1. **Lock mismatch.** "Kunci slot" is checked but the item does not fit the selected slot (for example a ring pasted while Helmet is selected). Expected: the server error shows in the verdict area, and nothing is recorded to any slot history. Pinned in Task 2, `test_lock_mismatch_shows_error_and_records_nothing`.
2. **Bad verdict on an empty slot.** Auto-scan of an item with `REJECT` or `INSUFFICIENT_DATA` into an empty slot, with the auto-equip toggle on. Expected: no `/api/equip-item` call. Pinned in Task 2, `test_autoscan_does_not_equip_unless_auto_equip_ok`.
3. **Second ring slot.** Auto-scan of a ring where the server chose `ring2` while the UI has `ring1` selected. Expected: the history is recorded under `ring2` and the selected slot switches to `ring2`. Pinned in Task 2, `test_autoscan_records_under_server_slot`.
4. **Sparse responses.** `ALREADY_EQUIPPED`, `engine: "none"` or responses with empty `dims` and no `guide`. Expected: the card renders without `NaN%`, `undefined` or `null` text. Pinned in Task 3, `test_card_sparse_response_has_no_placeholder_garbage`.
5. **Invalid regex.** An invalid regex in the rule editor. Expected: the server error is shown and the guide's stored rules are unchanged. Pinned in Task 4, `test_rule_editor_invalid_regex_keeps_rules`. The server side is already covered.

---

### Task 1: Server response fields for the UI

**Files:**
- Modify: `companion/equipment/evaluation.py`. Changes: `GuideSignal`; `EvaluationResult`; the ALREADY_EQUIPPED return (~line 204); the `current_raw` parse for the chosen slot.
- Modify: `companion/dashboard_api.py`. Changes: `flatten_result` (line 42); `evaluate_item_payload` (drop the second `get_current_item_info` lookup); `engine_status` in `get_dashboard_status` (~line 535).
- Create: `tests/unit/conftest.py`. Move into it the shared evaluation fixtures that `tests/unit/test_dashboard_api.py` currently imports from `tests/unit/equipment/test_evaluation.py`.
- Test: `tests/unit/equipment/test_evaluation.py`, `tests/unit/test_dashboard_api.py`

**Interfaces:**
- Produces:
  - `GuideSignal.priority_matched: int | None = None` and `GuideSignal.priority_total: int | None = None`. Fill them from `PrioritySignal.matched` and `.total`.
  - `EvaluationResult.current_item_base_type: str = ""`, the base type of the item currently in the chosen slot.
  - `flatten_result(r: EvaluationResult) -> dict`. The `current_base_type` parameter is removed. These keys are added:
    - `dps_pct: float` and `ehp_pct: float`: the chosen slot's values, 0.0 when there is no chosen SlotResult.
    - `slot_empty: bool`: the chosen `SlotResult.is_empty`, False when absent.
    - `auto_equip_ok: bool`, which is `verdict == "EQUIP_NOW" and slot_empty`.
    - `current_item_base_type` now comes from `r.current_item_base_type`.
  - `/api/status` → `engine_status.unavailable_reason: str | None`, taken from the session's `unavailable_reason`.
  - On ALREADY_EQUIPPED, `per_slot == [SlotResult(slot=slot, verdict="ALREADY_EQUIPPED")]`, never empty.

- [ ] **Step 1: Write failing tests**
  - In `test_evaluation.py`:
    - `test_guide_signal_carries_priority_counts`: the existing priority fixture gives `r.guide.priority_matched == <matched>`, `r.guide.priority_total == <total>` and `r.guide.priority_match == matched/total`.
    - `test_already_equipped_has_chosen_per_slot`: `r.verdict == "ALREADY_EQUIPPED"`, `[s.slot for s in r.per_slot] == [r.slot]`.
    - `test_current_item_base_type_on_result`: in the non-empty slot fixture, `r.current_item_base_type` equals the equipped item's base type.
  - In `test_dashboard_api.py`:
    - `test_flatten_auto_equip_ok_only_for_equip_now_into_empty`. Build table cases with `EvaluationResult` / `SlotResult` directly; expected `auto_equip_ok`:
      - (EQUIP_NOW, empty): True
      - (EQUIP_NOW, not empty): False
      - (CONDITIONAL_UPGRADE, empty): False
      - (REJECT, empty): False
      - (INSUFFICIENT_DATA, empty): False
    - `test_flatten_pct_and_empty_defaults`: when per_slot has no chosen slot, `dps_pct == 0.0`, `ehp_pct == 0.0`, `slot_empty is False` and `auto_equip_ok is False`.
    - `test_status_reports_unavailable_reason`: a fake session with `unavailable_reason="Docker daemon is not running (zero-backend fallback active)"` appears verbatim in `engine_status["unavailable_reason"]`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/equipment/test_evaluation.py tests/unit/test_dashboard_api.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the Interfaces above. Then move the shared fixtures to `tests/unit/conftest.py` and delete the cross-test-module import.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat(api): expose pct, slot_empty, auto_equip_ok, priority counts, unavailable_reason`

### Task 2: Playwright harness and server-owned slot in compare.js (#5, #11, #18)

**Files:**
- Create: `tests/e2e/__init__.py` (empty) and `tests/e2e/conftest.py`. The conftest provides:
  - a `dashboard_page` fixture: serve `dashboard/` with `http.server.ThreadingHTTPServer` on a free port in a daemon thread; launch Chromium headless (`p.chromium.launch()`); `pytest.skip` if the launch raises.
  - a `mock_api(page, responses: dict[str, dict | Callable[[dict], dict]])` helper. It installs `page.route("**/api/**", …)`, answers each path from `responses` (default `{}`), and records every request as `(path, json_body)` in a list it returns.
- Create: `tests/e2e/test_compare_slots.py`
- Modify: `dashboard/js/compare.js`. Changes:
  - `detectSlotFromItemText` (line 38);
  - the paste and run-compare handlers (~395-435);
  - `simulateVersusComparison` (~484);
  - the auto-scan poll (~575-620).
- Modify: `dashboard/index.html`: add a `<label><input type="checkbox" id="compare-lock-slot"> Kunci slot</label>` next to `#btn-run-compare`, unchecked by default.

**Interfaces:**
- Consumes: Task 1's `slot`, `auto_equip_ok`.
- Produces:
  - `mock_api` and `dashboard_page`, which Tasks 3 and 4 reuse.
  - `simulateVersusComparison(rawText, container, explicitSlot = null)` keeps its signature. It sends `slot` only when `#compare-lock-slot` is checked; the locked slot is then `appState.selectedSlot`.

- [ ] **Step 1: Write failing E2E tests** in `test_compare_slots.py`. Use ring/crossbow item texts copied from `tests/integration/equipment/test_pob2_live_weapon_integration.py`.
  - `test_manual_compare_sends_no_slot_when_unlocked`: paste a ring and click run. The recorded `/api/evaluate-item` body has no `slot` key.
  - `test_manual_compare_sends_selected_slot_when_locked`: check `#compare-lock-slot` with `ring2` selected. The body has `slot == "ring2"`.
  - `test_lock_mismatch_shows_error_and_records_nothing`: the mock returns `{"error": "Slot terkunci tidak cocok dengan item"}`. The text appears in `#compare-verdict-result`, and `localStorage` slot history is unchanged.
  - `test_autoscan_records_under_server_slot`: the clipboard-poll mock returns `has_new_item: true`, `slot: "ring2"` and `auto_equip_ok: false`, with `ring1` selected. The history entry is under `ring2` and the selected slot becomes `ring2`.
  - `test_autoscan_does_not_equip_unless_auto_equip_ok`: the auto-equip toggle is on and the poll returns `verdict: "REJECT"`, `slot_empty: true` and `auto_equip_ok: false`. There is no `/api/equip-item` request.
  - `test_autoscan_equips_server_slot_when_ok`: the poll returns `slot: "set2_main_hand"` and `auto_equip_ok: true`. `/api/equip-item` is called with `slot == "set2_main_hand"`.
  - `test_detect_slot_uses_item_class_table`: call `detectSlotFromItemText` via `page.evaluate` on an imported module. Expected results:
    - `"Item Class: Staves\nRarity: Normal\n--------"` gives `main_hand`;
    - `"Item Class: Quarterstaves"` gives `main_hand`;
    - `"Item Class: Rings"` gives `ring1`.
- [ ] **Step 2: Run** `uv run pytest tests/e2e -q`. Expected: tests FAIL. The harness itself must work: page loads, no console errors from the mocked `{}` defaults. If the defaults break page init, add the minimal canned responses in the conftest.
- [ ] **Step 3: Implement.**
  - **`detectSlotFromItemText`.** Map the `Item Class:` value through one explicit table of official PoE2 classes to UI slot keys, before any base-type substring guess. This fixes #18. The table must include:
    - Staves, Quarterstaves, Wands, Sceptres, Crossbows, Bows, One/Two Hand Maces/Swords/Axes, Spears, Flails, Talismans → `main_hand`
    - Foci, Shields, Bucklers, Quivers → `off_hand`
    - Rings, Amulets, Belts, Helmets, Gloves, Boots, Body Armours → the matching slot

    The function now only feeds the loading label and the lock target.
  - **`simulateVersusComparison`.**
    - Remove `WEAPON_UI_SLOTS` gating; send `slot` only when locked.
    - Record and select under `data.slot` only. Never fall back to the detected slot on success.
    - On `data.error`, render the error and record nothing.
  - **Auto-scan.**
    - Delete the `data.slot = targetSlot` overwrite and the local-loadout `isSlotEmpty` block.
    - Equip when `toggleAutoEquip.checked && data.auto_equip_ok`, to `data.slot`.
    - Record and notify under `data.slot`.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass, including `tests/e2e`.
- [ ] **Step 5: Commit** `feat(dashboard): server-owned slot for compare and auto-scan, verdict-gated auto-equip, Playwright harness`

### Task 3: Verdict card and engine header

**Files:**
- Modify: `dashboard/js/compare.js` `renderEvaluationVerdict` (line 659)
- Modify: `dashboard/js/runtime.js` (status badge, line ~19) and `dashboard/index.html` if a header element is needed
- Test: `tests/e2e/test_verdict_card.py`

**Interfaces:**
- Consumes these Task 1 keys: `slot`, `slot_reason`, `dps_pct`, `ehp_pct`, `guide.{name,stage_title,priority_matched,priority_total,must_have_missing,target_fit}`, `safety`, `engine`, `engine_reason`, and `/api/status` → `engine_status.unavailable_reason`.

Exact copy, with the server-supplied pieces inserted:
- Slot line: `🎯 Slot: <SLOT_LABELS[slot]> — <slot_reason>`
- Deltas: `DPS +1.2% · EHP −0.4%`. Each value is `(v*100).toFixed(1)` with an explicit sign; a negative value uses `−` (U+2212). Shown only when `engine` is `pob2` or `heuristic`.
- Priority: `Prioritas guide 3/4 (kurang: Movement Speed)`. The parenthetical is omitted when `must_have_missing` is empty. The whole line is omitted when `priority_total` is null or 0.
- Target fit (Phase 4 data, render only if present): `Di build target: DPS +x% · EHP +y%`
- Safety badge, one per entry in `safety`: `⛔ <reason>`
- Engine: keep the existing heuristic badge, with `engine_reason` appended after ` — ` when present.
- Header: when `engine_status.available` is false and `unavailable_reason` is set, the status badge reads `PoB2 OFF: <unavailable_reason>`. Otherwise the existing text stays.

- [ ] **Step 1: Write failing E2E tests**
  - `test_card_shows_slot_reason_and_pcts`: response `dps_pct: 0.0123`, `ehp_pct: -0.004`, `engine: "pob2"`. The card text contains `DPS +1.2%` and `EHP −0.4%` plus the slot_reason string.
  - `test_card_priority_line`: `guide.priority_matched: 3`, `priority_total: 4` and `must_have_missing: ["Movement Speed"]` give the exact text `Prioritas guide 3/4 (kurang: Movement Speed)`.
  - `test_card_safety_badge`: `safety: ["Fire damage ke Attack menyalakan Oil Grenade terlalu cepat (Fubgun, lvl 52+)"]`. A `⛔` badge with that text is present.
  - `test_card_sparse_response_has_no_placeholder_garbage`. Responses:
    - `{verdict: "ALREADY_EQUIPPED", engine: "none", dims: {}, guide: null, safety: []}`
    - an `INSUFFICIENT_DATA` heuristic weapon response

    Card text contains none of `NaN`, `undefined`, `null`.
  - `test_header_shows_unavailable_reason`: `/api/status` with `engine_status: {available: false, unavailable_reason: "Docker daemon is not running (zero-backend fallback active)"}`. The status badge contains that reason.
- [ ] **Step 2: Run** `uv run pytest tests/e2e/test_verdict_card.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the copy above in `renderEvaluationVerdict` and the status badge.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat(dashboard): verdict card shows slot reason, pct deltas, guide priority, safety, engine reason`

### Task 4: Guide tab: breaker-rule editor and re-import link

**Files:**
- Modify: `dashboard/js/guides.js`, `dashboard/index.html` (guide tab, ~line 613-622)
- Modify: `dashboard/js/controls.js`. On character switch, show the error when `/api/select-character` is non-OK, instead of ignoring it.
- Test: `tests/e2e/test_guide_tab.py`, `tests/unit/builds/` (known_rules defaults test)

**Interfaces:**
- Consumes:
  - `GET /api/guides` returns `guides[].breaker_rules`, where each rule is `{pattern, from_level, exclude_slots, reason}`, plus `guides[].source_url`.
  - `POST /api/guides/rules {slug, rules}` returns `{success: true}` or `{error}`.
- Produces: no new server API.

UI per guide row in `#guide-list`:
- **Existing:** name, stage count, PoB flag, Hapus.
- **New:**
  - a `Buka halaman guide` link to `source_url` (target `_blank`, `rel="noopener"`). It is for re-import via the bookmarklet and is hidden when there is no `source_url`.
  - an `Aturan (n)` toggle that expands a rule list. Each rule shows its `reason`, `pattern`, `from_level` and `exclude_slots`, with a `Hapus` button.
  - an add form with the fields: pattern, from_level (number), exclude_slots (comma-separated canonical slot names) and reason.
  - a `Simpan aturan` button. It POSTs the full rule list and shows the server error verbatim if there is one.
- **Hint text under the editor:** `Impor ulang guide Fubgun tanpa aturan akan memasang aturan bawaan lagi.` This documents the ledger's T2 behaviour.
- **guides.js:** `await` `refreshGuides()` and `refreshGuideControls()` after import and delete. This is a ledger T9 carry-over.

- [ ] **Step 1: Write failing tests**
  - `tests/unit/builds/test_known_rules.py::test_defaults_only_when_no_rules`:
    - importing the Fubgun fixture when stored rules already exist keeps those rules;
    - importing the Navira fixture gives `breaker_rules == []`.
    - Use `import_guide_payload` with `tmp_path` and the existing guide fixtures in `tests/fixtures/guides/`.
  - `tests/e2e/test_guide_tab.py`:
    - `test_rule_editor_add_and_save_posts_full_list`: one existing rule, plus one added via the form. The recorded `/api/guides/rules` body has `slug` and both rules, with `from_level` as an int and `exclude_slots` as a list.
    - `test_rule_editor_invalid_regex_keeps_rules`: the mock returns `{"error": "Pola regex tidak valid: ..."}`. The error is shown and the rendered list still has the original rule.
    - `test_reimport_link_points_to_source_url`: the link `href` equals `source_url`.
- [ ] **Step 2: Run** `uv run pytest tests/e2e/test_guide_tab.py tests/unit/builds/test_known_rules.py -q`. Expected: the e2e tests FAIL. The known_rules test may already pass; it is a regression pin, so keep it.
- [ ] **Step 3: Implement** the UI above, and fix the select-character error in controls.js.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat(dashboard): breaker-rule editor and re-import link in guide tab`

### End-of-phase check (controller, not a subagent task)

Run in the browser pane against the real dashboard (`.claude/launch.json` → `dashboard`):
- **Manual compare, unlocked.** Ring, crossbow and staff each land under the server slot.
- **Manual compare, locked.** Locked to a wrong slot, it shows the server error.
- **Verdict card.** It shows the slot reason and percentages, plus the safety badge for the Fubgun fire-to-attacks gloves (lvl ≥ 52 character or stage override).
- **Guide tab.** Add a rule, save, reload: the rule persists. Then delete it.
- **Header.** With Docker off, the header shows the PoB2 unavailable reason.

Restore any assignment or rule changed during the check.
