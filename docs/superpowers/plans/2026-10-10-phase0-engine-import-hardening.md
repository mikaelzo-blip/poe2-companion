# Phase 0 — PoB2 Engine & Character Import Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the data layer under item comparison. Stop leaking PoB2 Docker engines, keep the PoB2 baseline fresh, import "current" items and character stats faithfully, and surface GGG/OAuth errors honestly.

**Architecture:** Lifecycle and freshness live in `Pob2EquipmentSession` and the session cache in `dashboard_server.py`. GGG item JSON becomes clipboard-format text in one function in `api_adapter.py`. A new `session_import.py` writes PoB2-derived item text and baseline into `runtime/`. `dashboard_api.py` gets the character list from the MCP API, and import errors are reported verbatim.

**Tech Stack:** Python 3.11, pydantic v2, pytest, `uv`. The PoB2 MCP modules (`pob_mcp.poe_api`, `pob_mcp.poe_oauth`) are imported from `../path-of-building-2-mcp/server`.

**Spec:** `docs/superpowers/specs/2026-10-10-multi-guide-evaluation-design.md` (§6, §7, §9; audit findings #3 #4 #9 #12 #13 #14)

## Global Constraints

- Run tests with `uv run pytest -q`. The full suite must be green at the end of every task.
- No new dependencies.
- UI/user-facing messages in Indonesian. Code, comments and log messages in English.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- No `except: pass` on paths touched by this plan. Log with `logging.getLogger(__name__)`.
- The MCP backend may be absent (no `POB2_MCP_PATH`, no sibling dir). Every code path must work and return an explicit error or fallback in that case.
- The PoB engine exposes no attributes (Str/Dex/Int), so the baseline attributes are not filled from PoB2 (spec §7 is narrowed accordingly).

## Review Focus

1. **A GGG sync fails** (429, network down) during refresh or after an import. The session stays cached and usable with its previous baseline and is not closed. Tested in Task 1 and Task 2.
2. **The status poll fires every 2 s while a sync is running.** At most one sync thread per character. Tested in Task 2.
3. **GGG items without `name`** (magic/normal), uniques, items without properties or requirements, and properties with several values. Tested in Task 3.
4. **Import while PoB2 is unavailable.** The loadout is still written from adapter text, and existing non-manual baseline facts are kept but marked stale, not erased. Tested in Task 4.
5. **OAuth token missing or expired.** The character list still returns local characters, and `fetch_public_profile` returns `OAUTH_REQUIRED` without raising. Tested in Task 6.

---

### Task 1: PoB2 session lifecycle — no orphaned engines

**Files:**
- Modify: `companion/equipment/pob2_equipment_advisor.py` (`initialize`, new `load_pob_mcp_modules`)
- Modify: `companion/dashboard_server.py` (`get_or_create_pob_session`, `invalidate_pob_session`)
- Test: `tests/unit/equipment/test_pob2_session_lifecycle.py` (new)

**Interfaces:**
- Produces:
  - `load_pob_mcp_modules(backend_path: Path | None = None) -> tuple[ModuleType, ModuleType] | None` returns `(poe_api, poe_oauth)`, or `None` when the backend is missing or the import fails. It also adds the import dir to `sys.path` once.
  - `Pob2EquipmentSession.initialize()` calls `self.close()` on every failure path reached after any engine was constructed.
  - `invalidate_pob_session(character_id: str | None = None) -> None`: with an id, calls `sess.sync_character()` and **keeps** the session cached whatever the result. Without an id, `close()`s every cached session, then clears the caches.
  - `get_or_create_pob_session(...)`: an existing cached session that is unavailable or mismatched is `close()`d and removed before a new one is created. A new session whose `initialize()` returns False is never cached.

- [ ] **Step 1: Write failing tests**

```python
class CountingEngine:  # minimal engine: records calls, counts close()
    def __init__(self, fail_on=None): self.closed = 0; self.fail_on = fail_on
    def call(self, cmd, **kw):
        if cmd == self.fail_on: raise RuntimeError("boom")
        return {"xml": "<x/>", "className": "Mercenary", "level": 30} if cmd == "import_character" else {}
    def close(self): self.closed += 1

def test_initialize_failure_closes_both_engines():
    engines = []
    def factory():
        e = CountingEngine(fail_on="import_character"); engines.append(e); return e
    sess = Pob2EquipmentSession("X", engine_factory=factory, poe_api_client=MagicMock())
    assert sess.initialize() is False
    assert [e.closed for e in engines] == [1, 1]

def test_invalidate_syncs_and_keeps_session(monkeypatch):
    sess = MagicMock(); sess.sync_character.return_value = False
    monkeypatch.setitem(dashboard_server._GLOBAL_POB_SESSIONS, "X", sess)
    dashboard_server.invalidate_pob_session("X")
    sess.sync_character.assert_called_once()
    sess.close.assert_not_called()
    assert dashboard_server._GLOBAL_POB_SESSIONS["X"] is sess

def test_invalidate_all_closes_every_session(monkeypatch):
    a, b = MagicMock(), MagicMock()
    monkeypatch.setattr(dashboard_server, "_GLOBAL_POB_SESSIONS", {"A": a, "B": b})
    dashboard_server.invalidate_pob_session()
    a.close.assert_called_once(); b.close.assert_called_once()
    assert dashboard_server._GLOBAL_POB_SESSIONS == {}

def test_get_or_create_closes_unavailable_cached_session(monkeypatch):
    stale = MagicMock(is_available=False, character_name="X")
    monkeypatch.setattr(dashboard_server, "_GLOBAL_POB_SESSIONS", {"X": stale})
    monkeypatch.setattr(dashboard_server, "_FAILED_CHARACTERS", {})
    fresh = MagicMock(); fresh.initialize.return_value = False
    monkeypatch.setattr("companion.equipment.pob2_equipment_advisor.Pob2EquipmentSession", lambda **kw: fresh)
    monkeypatch.setattr(dashboard_server, "normalize_char_id", lambda c: c)
    assert dashboard_server.get_or_create_pob_session("X", force_retry=True) is None
    stale.close.assert_called_once()
    assert "X" not in dashboard_server._GLOBAL_POB_SESSIONS
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/equipment/test_pob2_session_lifecycle.py -v`. Expected: 4 FAIL.

- [ ] **Step 3: Implement the lifecycle changes above.** In `initialize()`, the live path and the injected-mock path both call `self.close()` in their `except` branches after an engine exists. `close()` must preserve `unavailable_reason`, so set the reason first and close second. `load_pob_mcp_modules` replaces the inline `sys.path` and import block in `initialize()`.

- [ ] **Step 4: Run** the new tests, then `uv run pytest -q`. Expected: all pass. `test_dashboard_server_equip_item_syncs_to_global_pob_session` still passes.

- [ ] **Step 5: Commit** — `fix(pob2): close engines on failed init and stop discarding sessions on invalidate`

---

### Task 2: Session freshness and effective character level

**Files:**
- Modify: `companion/equipment/pob2_equipment_advisor.py` (`last_synced_at`, `needs_refresh`)
- Modify: `companion/dashboard_server.py` (`maybe_refresh_pob_session`, called from `_api_status`)
- Modify: `companion/dashboard_api.py` (`character_level_and_zone`, `_build_eval_context` effective level)
- Test: `tests/unit/equipment/test_pob2_session_freshness.py` (new)

**Interfaces:**
- Consumes: Task 1 lifecycle.
- Produces:
  - `Pob2EquipmentSession.last_synced_at: float` (`time.monotonic()`), set by successful `initialize()` and `sync_character()`.
  - `Pob2EquipmentSession.needs_refresh(level: int | None, zone: str | None, max_age_s: float = 600.0, now: float | None = None) -> bool`. True when `level` exceeds `self.level`, or `zone` is non-None and differs from the zone seen on the previous call, or the age is above `max_age_s`. The first call records the zone and does not count as a change.
  - `character_level_and_zone(char_data: dict) -> tuple[int | None, str | None]` reads `level` and `current_zone` (either `{"value": ...}` or plain).
  - `maybe_refresh_pob_session(character_id: str, level: int | None, zone: str | None, spawn: Callable[[Callable[[], None]], None] = _spawn_daemon) -> bool` returns True if a refresh was started. The refresh thread runs `sess.sync_character()` and then `apply_session_to_runtime` (Task 5; until Task 5 lands, only the sync). At most one in flight per character, tracked by a `set` guarded by a lock.
  - `_build_eval_context`: `char_level = max(session_level, file_level)`, ignoring Nones.

- [ ] **Step 1: Write failing tests**

```python
def test_needs_refresh_on_level_up_zone_change_and_age():
    s = Pob2EquipmentSession("X"); s.level = 37; s.last_synced_at = 1000.0
    assert s.needs_refresh(37, "G2_1", now=1001.0) is False      # first zone observation
    assert s.needs_refresh(38, "G2_1", now=1001.0) is True
    assert s.needs_refresh(37, "G2_2", now=1001.0) is True
    assert s.needs_refresh(37, "G2_2", now=1000.0 + 601) is True

def test_maybe_refresh_runs_one_sync_at_a_time(monkeypatch):
    sess = MagicMock(); sess.needs_refresh.return_value = True
    monkeypatch.setitem(dashboard_server._GLOBAL_POB_SESSIONS, "X", sess)
    pending = []
    assert dashboard_server.maybe_refresh_pob_session("X", 40, None, spawn=pending.append) is True
    assert dashboard_server.maybe_refresh_pob_session("X", 40, None, spawn=pending.append) is False
    pending[0]()                                            # run the queued refresh
    sess.sync_character.assert_called_once()
    assert dashboard_server.maybe_refresh_pob_session("X", 40, None, spawn=pending.append) is True

def test_refresh_sync_failure_keeps_session(monkeypatch):
    sess = MagicMock(); sess.needs_refresh.return_value = True; sess.sync_character.return_value = False
    monkeypatch.setitem(dashboard_server._GLOBAL_POB_SESSIONS, "X", sess)
    dashboard_server.maybe_refresh_pob_session("X", 40, None, spawn=lambda fn: fn())
    sess.close.assert_not_called()
    assert dashboard_server._GLOBAL_POB_SESSIONS["X"] is sess

def test_effective_level_prefers_newer_character_file(tmp_path):
    (tmp_path / "characters").mkdir()
    (tmp_path / "characters" / "X.json").write_text(json.dumps({"level": {"value": 53}}))
    ctx = _build_eval_context({"character_id": "X", "stage": "auto"}, SAMPLE_BOOTS_TEXT, tmp_path, MagicMock(level=37))
    assert ctx.char_level == 53
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/equipment/test_pob2_session_freshness.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement the interfaces above.** In `_api_status`, after `get_dashboard_status(...)` returns, call `maybe_refresh_pob_session(char_id, *character_level_and_zone(data["character"]))` when a cached session exists. `_build_eval_context` reuses `character_level_and_zone` instead of its inline level/zone parsing.

- [ ] **Step 4: Run** the new tests, then `uv run pytest -q`. Expected: all pass.

- [ ] **Step 5: Commit** — `feat(pob2): refresh session on level/zone change and use newest character level`

---

### Task 3: GGG item JSON to clipboard-format text

**Files:**
- Modify: `companion/equipment/api_adapter.py` (new `clean_markup`, `ggg_item_to_text`; `parse_character_payload` uses them)
- Test: `tests/unit/equipment/test_ggg_item_text.py` (new) with fixture `tests/fixtures/ggg/items.json`

**Interfaces:**
- Produces:
  - `clean_markup(text: str) -> str`: the three regexes from `pob_mcp.poe_api._clean_mod` (`<..>{x}`→`x`, `[a|b]`→`b`, `[a]`→`a`).
  - `ggg_item_to_text(item: dict) -> str` mirrors the in-game clipboard layout:
    1. `Item Class: <plural>`, where the class label is the first property with empty `values`, cleaned, then mapped through `ITEM_CLASS_PLURAL`.
    2. `Rarity: <item["rarity"] or frame map>`.
    3. For rare/unique, a `name` line, then a `baseType` line. For magic/normal, only `typeLine`.
    4. A property block `Name: v1, v2` for properties with values.
    5. `Requirements:` with lines like `Level: 28` / `Dex: 10`.
    6. `Item Level: <ilvl>`.
    7. Mod blocks, each separated by `--------`: enchant `(enchant)`, rune `(rune)`, implicit `(implicit)`, explicit, crafted, fractured `(fractured)`, desecrated `(desecrated)`, mutated. Every mod is passed through `clean_markup`.
  - `ITEM_CLASS_PLURAL: dict[str, str]` covers at least: Helmet→Helmets, Body Armour→Body Armours, Gloves, Boots, Belt→Belts, Amulet→Amulets, Ring→Rings, Staff→Staves, Quarterstaff→Quarterstaves, Crossbow→Crossbows, Bow→Bows, Wand→Wands, Sceptre→Sceptres, Focus→Foci, Shield→Shields, Buckler→Bucklers, Quiver→Quivers, Spear→Spears, Flail→Flails, Talisman→Talismans, One Hand Mace→One Hand Maces, Two Hand Mace→Two Hand Maces. The fallback is `label + "s"`.

- [ ] **Step 1: Create the fixture** `tests/fixtures/ggg/items.json`: a list with
  - a rare `Helm` (Face Mask, properties `Helmet`, `[Evasion|Evasion Rating]` 37, `[EnergyShield|Energy Shield]` 18; requirements Level 28, `[Dexterity|Dex]` 10; ilvl 40; 2 explicit mods, one containing `[Resistances|Fire Resistance]` markup),
  - a magic `Ring2` (no `name`, typeLine `Smouldering Iron Ring of the Starfish`, baseType `Iron Ring`, implicit `Adds 1 to 4 Physical Damage to Attacks`),
  - a rare `Weapon` (`[Staff]` class property, no other properties, `desecratedMods` with one mod),
  - a unique `BodyArmour` with property `Armour` values `[["120",1],["15",1]]`.
  The shapes are copied from a real `fetch_character_raw` response (keys: `name, typeLine, baseType, rarity, frameType, ilvl, properties[{name, values, displayMode, type}], requirements[...]`).

- [ ] **Step 2: Write failing tests**

```python
def test_rare_helm_text(items):
    text = ggg_item_to_text(items[0])
    assert text.splitlines()[:4] == ["Item Class: Helmets", "Rarity: Rare", "Plague Crest", "Face Mask"]
    assert "Evasion Rating: 37" in text and "Energy Shield: 18" in text
    assert "Requirements:" in text and "Level: 28" in text and "Dex: 10" in text
    assert "Item Level: 40" in text
    assert "+23% to Fire Resistance" in text and "[" not in text

def test_magic_ring_single_header_line(items):
    lines = ggg_item_to_text(items[1]).splitlines()
    assert lines[:3] == ["Item Class: Rings", "Rarity: Magic", "Smouldering Iron Ring of the Starfish"]
    assert "Adds 1 to 4 Physical Damage to Attacks (implicit)" in lines

def test_desecrated_and_multi_value_properties(items):
    assert "(desecrated)" in ggg_item_to_text(items[2])
    assert "Item Class: Staves" in ggg_item_to_text(items[2])
    assert "Armour: 120, 15" in ggg_item_to_text(items[3])

def test_text_round_trips_through_parser(items):
    parsed = parse_item_text(ggg_item_to_text(items[0]))
    assert parsed.base_type == "Face Mask" and parsed.slot == SlotType.HELMET
```

- [ ] **Step 3: Run** `uv run pytest tests/unit/equipment/test_ggg_item_text.py -v`. Expected: FAIL (no `ggg_item_to_text`).

- [ ] **Step 4: Implement** `clean_markup`, `ITEM_CLASS_PLURAL` and `ggg_item_to_text`, and replace the inline `lines = [...]` construction in `parse_character_payload` with `ggg_item_to_text(raw_item)`. Keep its `name`/`typeLine` empty-item skip.

- [ ] **Step 5: Run** the new tests, then `uv run pytest -q`. Existing import tests must pass, and their payloads (no `properties`, no `rarity`) must still produce parseable text.

- [ ] **Step 6: Commit** — `fix(import): build full clipboard-format text from GGG item JSON`

---

### Task 4: Official import replaces gear and protects only manual baseline facts

**Files:**
- Modify: `companion/equipment/api_adapter.py` (`parse_character_payload`)
- Modify: `companion/dashboard_api.py` (`import_character_payload` baseline merge)
- Test: `tests/unit/test_dashboard_api.py` (add tests)

**Interfaces:**
- Produces:
  - `parse_character_payload(..., overwrite_conflicts=True)` starts from `EquippedLoadout.create_draft` **without** copying `current_loadout` slots, so slots absent from the payload end up empty. With `overwrite_conflicts=False`, the current copy + conflict-detection behaviour is unchanged.
  - Baseline merge in `import_character_payload`, for each baseline fact name:
    - the old fact has `source == MANUAL_USER_INPUT` → keep the old fact;
    - otherwise, the new fact is known → use the new fact;
    - otherwise, the old fact is known → keep `old.mark_stale()`.

- [ ] **Step 1: Write failing tests**

```python
def test_official_import_clears_slots_missing_from_payload(tmp_path):
    first = {"items": [boots_item(), gloves_item()]}
    second = {"items": [boots_item()]}
    import_character_payload({"character_id": "T", "character_data": first, "overwrite": True}, tmp_path)
    import_character_payload({"character_id": "T", "character_data": second, "overwrite": True}, tmp_path)
    lo = load_loadout(tmp_path, "T")
    assert lo.get_slot(SlotType.GLOVES) is None
    assert lo.get_slot(SlotType.BOOTS) is not None

def test_import_keeps_manual_facts_and_marks_others_stale(tmp_path):
    base = CharacterStatBaseline.create_empty(character_id="T", anchored_loadout_revision=1)
    base.life = CharacterFact[int].create(500, source=BaselineSource.MANUAL_USER_INPUT)
    base.raw_fire_res = CharacterFact[int].create(30, source=BaselineSource.GGG_OFFICIAL_API)
    save_baseline(tmp_path, base)
    import_character_payload({"character_id": "T", "character_data": {"items": [boots_item()]}}, tmp_path)
    after = load_baseline(tmp_path, "T")
    assert after.life.value == 500 and after.life.source == BaselineSource.MANUAL_USER_INPUT
    assert after.raw_fire_res.value == 30 and after.raw_fire_res.verification == VerificationState.STALE
```

(`boots_item()` / `gloves_item()` are small helpers in the test module that return GGG-shaped dicts with `inventoryId` `Boots` / `Gloves`.)

- [ ] **Step 2: Run** the two tests. Expected: FAIL. The ghost glove remains, and fire res is unchanged with no stale marker.

- [ ] **Step 3: Implement** the two behaviours above. `test_import_character_payload_overwrites_conflicting_manual_slot` must keep passing. If it asserts behaviour that contradicts "official import replaces gear", update its expectation and say so in the commit body.

- [ ] **Step 4: Run** `uv run pytest -q`. Expected: green.

- [ ] **Step 5: Commit** — `fix(import): official import replaces gear; only manual baseline facts are protected`

---

### Task 5: Write PoB2 item text and baseline into runtime after sync

**Files:**
- Create: `companion/equipment/session_import.py`
- Modify: `companion/dashboard_server.py` (call after import / fetch-profile / select / refresh)
- Test: `tests/unit/equipment/test_session_import.py` (new)

**Interfaces:**
- Consumes: Task 4 baseline merge rule (manual facts win), the `Pob2EquipmentSession` attributes `equipped_items`, `defenses_before`, `stats_before`, and `get_equipped_item(slot)`.
- Produces:
  - `apply_session_to_runtime(runtime_dir: Path, character_id: str, session: Any) -> list[str]`. Returns warnings and never raises. Steps:
    1. For each slot in `POB2_PRODUCTION_SLOTS` whose `session.get_equipped_item(slot)` is `{"equipped": True, "raw": <text>}`, map the PoB slot to `(SlotType, WeaponSetContext | None)` (Weapon 1/2 → set 1 main/off, `* Swap` → set 2, others shared), parse the raw text with `parse_item_text(raw, target_slot=..., target_weapon_set=...)`, and call `loadout.transition_slot(..., source=BaselineSource.GGG_OFFICIAL_API, verification=VerificationState.VERIFIED)`. If no loadout exists, create a draft, set the slots, and `finalize(loadout_id=f"pob2_{character_id}")`. Then `save_loadout`.
    2. Write baseline facts with source `DERIVED_CALCULATION`, `evidence_ref="pob2"`, except where the existing fact is manual:
       - `life` / `armour` / `evasion` / `energy_shield` / `mana` from `defenses_before`;
       - `raw_<el>_res` = `stats_before["defense"]["<El>Resist"]` and `effective_<el>_res` = `min(raw, max_<el>_res.value or 75)`, for fire/cold/lightning/chaos.
  - `dashboard_server`: `_api_import_character`, `_api_fetch_public_profile` and `_api_select_character` (after the session exists) and the refresh thread from Task 2 call `apply_session_to_runtime(RUNTIME_DIR, char_id, sess)` after a successful `sync_character()`.

- [ ] **Step 1: Write failing tests** (using `SyncFakePobEngine`-style data via a `MagicMock` session):

```python
def test_apply_session_writes_pob_item_text_and_baseline(tmp_path):
    sess = MagicMock()
    sess.get_equipped_item.side_effect = lambda s: {"equipped": True, "raw": HELM_RAW} if s == "Helmet" else {"equipped": False}
    sess.defenses_before = {"Life": 812, "Armour": 300, "Evasion": 450, "EnergyShield": 60, "Mana": 120, "TotalEHP": 3000}
    sess.stats_before = {"defense": {"FireResist": 82, "ColdResist": 40, "LightningResist": 75, "ChaosResist": -10}}
    assert apply_session_to_runtime(tmp_path, "T", sess) == []
    lo = load_loadout(tmp_path, "T")
    assert lo.get_slot(SlotType.HELMET).item.raw_text == HELM_RAW
    b = load_baseline(tmp_path, "T")
    assert b.life.value == 812 and b.raw_fire_res.value == 82 and b.effective_fire_res.value == 75

def test_apply_session_never_overwrites_manual_fact(tmp_path):
    ...  # baseline with manual life 500 saved first -> after apply, life == 500

def test_apply_session_reports_unparseable_item_as_warning(tmp_path):
    ...  # raw "garbage" for Helmet -> returns one warning mentioning "Helmet", nothing raised
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/equipment/test_session_import.py -v`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement** `session_import.py` and the server calls.

- [ ] **Step 4: Run** `uv run pytest -q`. Expected: green.

- [ ] **Step 5: Commit** — `feat(import): persist PoB2 item text and computed baseline after each sync`

---

### Task 6: Character list from GGG API and honest import errors

**Files:**
- Modify: `companion/dashboard_api.py` (`get_account_characters`, `fetch_public_profile`, new `_list_api_characters`)
- Modify: `tests/unit/test_dashboard_api.py` (replace `test_get_account_characters` and the three `test_fetch_public_profile_*` legacy tests)

**Interfaces:**
- Consumes: `load_pob_mcp_modules()` (Task 1).
- Produces:
  - `_list_api_characters(now: float | None = None) -> list[dict]` returns `[{"name", "level", "class", "league"}]` from `poe_api.list_characters()`, cached for 300 s in a module dict. It returns `[]` (and logs a warning) when the modules are missing, the token is invalid, or the API errors.
  - `get_account_characters(...)` merges `_list_api_characters()` (league from the API) with local `runtime/characters/*.json` (league `"Local"`, API entries win on name). It no longer reads `oauth_status.json` and no longer has the fake `BOMSHAK lvl 19` fallback; an empty list is a valid result. The response adds `"source": "api" | "local"`.
  - `fetch_public_profile(account_name, character_id, runtime_dir, overwrite=True)` returns:
    - MCP missing → `{"error": "POB2_MCP_NOT_FOUND", "message": "Folder path-of-building-2-mcp tidak ditemukan. Set POB2_MCP_PATH."}`;
    - no valid token → `{"error": "OAUTH_REQUIRED", "message": "Login PoE belum aktif/kedaluwarsa. Jalankan login via PoB2 MCP (poe_login_start)."}`;
    - API exception → `{"error": "GGG_API_ERROR", "message": str(exc)}`;
    - success → the `import_character_payload` result.
    The `character-window` fallback, the Chrome User-Agent and the 403/404 prose are deleted.

- [ ] **Step 1: Write failing tests**

```python
def test_account_characters_merge_api_and_local(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_api, "_list_api_characters", lambda now=None: [{"name": "BOMSHAK", "level": 60, "class": "Mercenary", "league": "Rise"}])
    (tmp_path / "characters").mkdir(); (tmp_path / "characters" / "Alt.json").write_text(json.dumps({"character_name": "Alt", "level": 5}))
    res = get_account_characters(runtime_dir=tmp_path)
    assert {c["name"]: c["league"] for c in res["characters"]} == {"BOMSHAK": "Rise", "Alt": "Local"}

def test_account_characters_no_fake_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_api, "_list_api_characters", lambda now=None: [])
    assert get_account_characters(runtime_dir=tmp_path)["characters"] == []

def test_list_api_characters_is_cached(monkeypatch):
    calls = []
    fake_api = SimpleNamespace(list_characters=lambda: calls.append(1) or [{"name": "A", "level": 1, "class": "W", "league": "S"}])
    fake_oauth = SimpleNamespace(get_valid_token=lambda: "t")
    monkeypatch.setattr(dashboard_api, "load_pob_mcp_modules", lambda: (fake_api, fake_oauth))
    dashboard_api._list_api_characters(now=0); dashboard_api._list_api_characters(now=100)
    assert len(calls) == 1

@pytest.mark.parametrize("modules, expected", [
    (None, "POB2_MCP_NOT_FOUND"),
    ((SimpleNamespace(), SimpleNamespace(get_valid_token=lambda: "")), "OAUTH_REQUIRED"),
    ((SimpleNamespace(fetch_character_raw=MagicMock(side_effect=RuntimeError("rate limited (429)"))),
      SimpleNamespace(get_valid_token=lambda: "t")), "GGG_API_ERROR"),
])
def test_fetch_public_profile_errors(tmp_path, monkeypatch, modules, expected):
    monkeypatch.setattr(dashboard_api, "load_pob_mcp_modules", lambda: modules)
    res = fetch_public_profile("acc", "BOMSHAK", tmp_path)
    assert res["error"] == expected
```

(`get_valid_token` in `pob_mcp` raises when not logged in. Treat both a raise and a falsy return as `OAUTH_REQUIRED`, and add that case to the parametrization.)

- [ ] **Step 2: Run** them. Expected: FAIL.

- [ ] **Step 3: Implement.** `dashboard_api` imports `load_pob_mcp_modules` at module level from `pob2_equipment_advisor` so tests can monkeypatch it. Delete the three legacy `fetch_public_profile` tests and the old `test_get_account_characters`.

- [ ] **Step 4: Run** `uv run pytest -q`. Expected: green. Check the dashboard character dropdown still works with an empty list by loading `/api/account-characters` in the browser pane against the dev server (`uv run python -m companion.cli dashboard --port 8091 --no-browser`).

- [ ] **Step 5: Commit** — `fix(import): character list from GGG API; surface OAuth/API errors instead of legacy fallback`

---

### Task 7: Live verification and docs

**Files:**
- Modify: `README.md` (Docker is required for the PoB2 engine; the MCP login step; what refresh does)
- Modify: `docs/audits/2026-10-10-COMPARE_AND_MCP_IMPORT_AUDIT.md` (mark #3 #4 #9 #12 #13 #14 as fixed, with commit hashes)

- [ ] **Step 1: Live check** (requires Docker and a valid MCP token; if either is missing, record that and skip):
  1. Start the dashboard.
  2. Note `docker ps --filter ancestor=<pob image> -q | wc -l`.
  3. Trigger "Sync" for the active character 3 times.
  4. The count must not grow.
  5. `runtime/loadouts/<char>.json` helmet `raw_text` must contain an `Item Level:` line and base defenses.
- [ ] **Step 2: Update README and the audit doc.**
- [ ] **Step 3: Commit** — `docs: phase 0 engine/import hardening notes`
