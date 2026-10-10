# Phase 1 — Guide Model, Bookmarklet & Guide Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build guides can be imported from mobalytics (via a bookmarklet) or from a PoB2 share code, stored as profiles with level-resolved stages, and managed from the dashboard. Verdicts do not change yet.

**Architecture:** New package `companion/builds/` with no dependency on the PoB engine or on verdict code. It contains models (`guide.py`), parsers (`mobalytics.py`, `pob_code.py`), stage resolution (`stages.py`) and persistence (`store.py`). The bookmarklet lives in `dashboard/bookmarklet.js`. The dashboard gets JSON endpoints and a minimal "Tambah Guide" tab.

**Tech Stack:** Python 3.11, pydantic v2, pytest, stdlib `zlib`/`base64`/`urllib`/`xml.etree`. Browser JS without libraries.

**Spec:** `docs/superpowers/specs/2026-10-10-multi-guide-evaluation-design.md` (§4, §8 partially)

## Global Constraints

- Run tests with `uv run pytest -q`. The suite is green after every task.
- No new dependencies.
- UI copy in Indonesian. Code, comments and logs in English.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The bookmarklet makes **no network requests**. It reads only `window.__PRELOADED_STATE__` of the page the user has open. Python never fetches mobalytics (HTTP 403 by design; do not work around it).
- Deviations from the spec, decided while planning:
  - The bookmarklet JSON carries trimmed fields (§4.1 listed raw `equipment`). The format is defined in Task 2.
  - The per-character guide selection is stored in `runtime/guides/_assignments.json`, not inside `runtime/characters/<id>.json` (§4.5). This avoids breaking `CharacterState` validation.
  - Delete and rule updates use `POST /api/guides/delete` and `POST /api/guides/rules`. The server only routes GET/POST.
  - The guide-priority logic (`priorities.py`) moves to Phase 2, where the policy consumes it.

## Review Focus

1. **Variants with `null` slots**, unique items (no base, no synthesizable text) and charms/flasks. The parser skips them without error and the stage keeps its other items. Tested in Task 3.
2. **Unparseable, duplicate or out-of-order stage titles, and single-variant guides.** Every level 1–100 resolves to exactly one auto stage. Tested in Task 4.
3. **Re-importing a guide keeps its breaker rules.** Tested in Task 1.
4. **Malformed paste** (random text, truncated JSON, invalid share code, wrong `format`). Gives a clear Indonesian error and writes nothing. Tested in Task 6.
5. **Hostile or odd guide names** (`../x`, emoji, empty). The slug is sanitized and files stay inside `runtime/guides/`. Tested in Task 1.

---

### Task 1: Guide models and store

**Files:**
- Create: `companion/builds/__init__.py`, `companion/builds/guide.py`, `companion/builds/store.py`
- Test: `tests/unit/builds/test_guide_store.py`

**Interfaces:**
- Produces (pydantic models in `guide.py`):
  ```python
  class StageItem(BaseModel):
      slot: str                      # canonical PoB slot: Helmet, Body Armour, Gloves, Boots, Amulet, Belt,
                                     # Ring 1, Ring 2, Weapon 1, Weapon 2, Weapon 1 Swap, Weapon 2 Swap
      name: str                      # base name, or unique name when is_unique
      item_class: str                # singular label, e.g. "Crossbow", "Boots"
      is_unique: bool = False
      base_stats: dict[str, str] = {}
      mods: list[str] = []
      must_have: list[str] = []
      raw_text: str | None = None    # None for uniques

  class BreakerRule(BaseModel):
      pattern: str                   # validated with re.compile at construction
      from_level: int = 1
      exclude_slots: list[str] = []
      reason: str

  class GuideStage(BaseModel):
      id: str
      title: str
      min_level: int = 1
      max_level: int = 100
      auto: bool = True              # False = reachable only via manual override
      items: dict[str, StageItem] = {}
      main_skill: str | None = None
      weapon_classes: dict[int, list[str]] = {}   # {1: ["Staff"], 2: ["Crossbow"]}

  class GuideProfile(BaseModel):
      slug: str
      name: str
      source_url: str | None = None
      imported_at: str               # ISO-8601 UTC
      stages: list[GuideStage]       # non-empty
      has_pob: bool = False
      pob_stage_id: str | None = None
      breaker_rules: list[BreakerRule] = []
  ```
- Produces (`store.py`, all paths under `runtime_dir / "guides"`):
  - `slugify(text: str) -> str`: lowercase `[a-z0-9-]`, runs collapsed, at most 60 chars. Raises `ValueError("Nama guide tidak valid")` when the result is empty.
  - `save_guide(runtime_dir: Path, profile: GuideProfile, pob_xml: str | None = None) -> GuideProfile`: when a guide with the same slug exists, the stored `breaker_rules` are kept (not the incoming ones). Writes `<slug>.json` and, if given, `<slug>.xml`. Returns the stored profile.
  - `load_guide(runtime_dir, slug) -> GuideProfile | None`, `load_guide_xml(runtime_dir, slug) -> str | None`, `list_guides(runtime_dir) -> list[GuideProfile]` (sorted by name), `delete_guide(runtime_dir, slug) -> bool`.
  - `set_breaker_rules(runtime_dir, slug, rules: list[BreakerRule]) -> GuideProfile`.
  - `get_assignment(runtime_dir, character_id) -> tuple[str | None, str | None]` returns `(guide_slug, stage_override)` from `_assignments.json`. A slug whose guide no longer exists is reported as `None`.
  - `set_assignment(runtime_dir, character_id, guide_slug: str | None, stage_override: str | None) -> None`.

- [ ] **Step 1: Write failing tests**: `slugify` cases (`"0.5.5 Fubgun Flameblast"`→`"0-5-5-fubgun-flameblast"`, `"../x"`→`"x"`, `"🔥"`→ValueError); a save/load round trip; re-save with an empty `breaker_rules` keeps the stored rules; `delete_guide` removes `.json` and `.xml`; assignment round trip; assignment to a deleted guide → `(None, None)`; `BreakerRule(pattern="(")` raises `ValidationError`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/builds/test_guide_store.py -v`. Expected: FAIL (package missing).
- [ ] **Step 3: Implement** `guide.py` and `store.py` (JSON via `model_dump_json(indent=2)`, UTF-8).
- [ ] **Step 4: Run** the tests, then `uv run pytest -q`. Expected: green.
- [ ] **Step 5: Commit** — `feat(builds): guide profile models and runtime store`

---

### Task 2: Bookmarklet and recorded guide fixtures

**Files:**
- Create: `dashboard/bookmarklet.js`
- Create: `tests/fixtures/guides/fubgun-flameblast-oil-grenade.json`, `tests/fixtures/guides/naviras-fracturing-varashta-league-starter.json`, `tests/fixtures/guides/plant-oracle-druid-leveling-build-guide.json`
- Test: `tests/unit/builds/test_guide_fixtures.py`

**Interfaces:**
- Produces: the bookmarklet output format `poe2-companion-guide/1`:
  ```json
  {"format": "poe2-companion-guide/1",
   "source_url": "<location.origin + location.pathname>",
   "slug": "<last path segment>",
   "name": "<doc.data.name>",
   "pob_code": "<doc.data.pobCode or null>",
   "variants": [
     {"id": "default-variant", "title": "lvl 1-14",
      "items": {"<key>": {"name": "...", "item_class": "<itemClassSlug>", "is_unique": false,
                           "stats": [["Armour", "74"]],
                           "mods": [{"text": "+60 to maximum Life", "must_have": false}]}},
      "skills": [{"name": "Explosive Grenade", "weapon_set": null}]}]}
  ```
  Item keys are `helmet, body, gloves, boots, amulet, belt, leftRing, rightRing, mainHand.set1, mainHand.set2, offHand.set1, offHand.set2`. Null slots and charms/flasks/`extraRing` are omitted.
- Extraction rules (from the live page structure, verified 2026-10-10):
  - Query = the entry of `__PRELOADED_STATE__.poe2State.apollo.graphqlV2.queries` whose `queryKey[0] === "ngf-ug-featured-document-page"` and `queryKey[2] === <slug>`.
  - `doc = query.state.data[0].game.documents.userGeneratedDocumentBySlug.data`.
  - Variants come from `doc.data.buildVariants.values`. Titles are joined by `id` from `doc.content[*].data.childrenVariants[*]` (`{id, title}`). A variant without a title gets `"Variant <n>"`.
  - An item comes from `slotEntry.commonItem` (weapons: `entry.set1/set2.commonItem`). `stats` from `commonItem.stats`, `mods` from `commonItem.explicitDescriptions[].description`/`mustHave`.
  - Skills come from `variant.skillGems.gems[].activeSkill.name` with `grantedByWeaponSet`.
- The file defines `function extractGuide(win)`, which returns the object or throws `Error("Format halaman tidak dikenal")`, plus a tail that copies `JSON.stringify(extractGuide(window))` with `navigator.clipboard.writeText` and `alert`s success or failure. Keep `extractGuide` callable on its own so it can be reused from the browser pane.

- [ ] **Step 1: Write `dashboard/bookmarklet.js`.**
- [ ] **Step 2: Record fixtures.** In the built-in browser pane, open each of the three URLs (spec §1). Run the contents of `bookmarklet.js` with the clipboard tail replaced by `return JSON.stringify(extractGuide(window))`, and save the result to the fixture path. These are the exact pages the user linked, viewed normally; no other requests are made.
- [ ] **Step 3: Write tests** for fixture sanity:
  - each fixture has `format == "poe2-companion-guide/1"` and ≥ 1 variant;
  - Fubgun has 9 variants titled `["lvl 1-14","lvl 15-32","lvl 33-51","lvl 52 Swap","lvl 53-68","lvl 85","Endgame","Mageblood","DoT Cap"]` and a non-null `pob_code`;
  - Plant Oracle has `pob_code is None`;
  - no fixture contains `iconURL` or `poe2TradeRequest` (trimming works).
- [ ] **Step 4: Run** `uv run pytest tests/unit/builds/test_guide_fixtures.py -v` and `node --check dashboard/bookmarklet.js`. Expected: PASS.
- [ ] **Step 5: Commit** — `feat(builds): mobalytics guide bookmarklet and recorded fixtures`

---

### Task 3: Mobalytics JSON to GuideProfile

**Files:**
- Create: `companion/builds/mobalytics.py`
- Test: `tests/unit/builds/test_mobalytics_parser.py`

**Interfaces:**
- Consumes: Task 1 models; `ITEM_CLASS_PLURAL` from `companion/equipment/api_adapter.py` (Phase 0 Task 3).
- Produces:
  - `MOBA_SLOT_MAP: dict[str, str]`: `helmet→Helmet, body→Body Armour, gloves→Gloves, boots→Boots, amulet→Amulet, belt→Belt, leftRing→Ring 1, rightRing→Ring 2, mainHand.set1→Weapon 1, offHand.set1→Weapon 2, mainHand.set2→Weapon 1 Swap, offHand.set2→Weapon 2 Swap`.
  - `ITEM_CLASS_SLUG_LABELS: dict[str, str]`: every `itemClassSlug` present in the three fixtures mapped to its singular PoE label (e.g. `crossbow→Crossbow`, `staff→Staff`, `boots→Boots`). An unknown slug becomes a title-cased label and is added to the warnings.
  - `parse_mobalytics_guide(data: dict) -> tuple[GuideProfile, str | None, list[str]]` returns `(profile_without_level_ranges, pob_code, warnings)`. It raises `ValueError` with an Indonesian message when `format` is wrong or there are no variants.
    - `stage.items`: non-unique items get `raw_text` synthesized as `Item Class: <plural>\nRarity: Rare\nGuide <slot>\n<name>\n--------\n<stat lines>\n--------\n<mods>`. Weapon `Minimum/Maximum Physical Damage` become one `Physical Damage: a-b` line, and other stats become `Name: value`. Uniques keep `raw_text=None`.
    - `stage.main_skill` = the first skill's name.
    - `stage.weapon_classes` = `{1: labels of Weapon 1/2, 2: labels of Weapon 1/2 Swap}`, with empty sets omitted.
    - `has_pob = pob_code is not None`, `pob_stage_id` = the last stage id.
  - Level ranges are not set here; Task 4 sets them. The function calls `stages.assign_level_ranges(profile)` before returning once Task 4 exists. Until then, the defaults are 1–100.

- [ ] **Step 1: Write failing tests** against the fixtures:
  - the Fubgun stage `"lvl 15-32"` has `items["Weapon 1"].name == "Varnished Crossbow"`, its `raw_text` parses with `parse_item_text` to slot `MAIN_HAND`, and `"Physical Damage: 18-54"` is in its raw text;
  - the Fubgun `"Endgame"` stage has `weapon_classes[1] == ["Staff"]` and `"Crossbow" in weapon_classes[2]` (the exact class labels come from the fixture; adjust only the label spelling, not the structure);
  - a unique body armour has `is_unique and raw_text is None`;
  - Plant Oracle gives 1 stage and `has_pob is False`;
  - `{"format": "x"}` raises `ValueError`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/builds/test_mobalytics_parser.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `mobalytics.py`.
- [ ] **Step 4: Run** the tests, then `uv run pytest -q`. Expected: green.
- [ ] **Step 5: Commit** — `feat(builds): parse mobalytics guide JSON into guide profiles`

---

### Task 4: Stage level ranges and stage resolution

**Files:**
- Create: `companion/builds/stages.py`
- Modify: `companion/builds/mobalytics.py` (call `assign_level_ranges`)
- Test: `tests/unit/builds/test_stages.py`

**Interfaces:**
- Produces:
  - `parse_level_range(title: str) -> tuple[int | None, int | None, bool]` returns `(min, max, is_endgame_keyword)`.
  - `assign_level_ranges(profile: GuideProfile) -> GuideProfile`: a new profile with `min_level`/`max_level`/`auto` set per spec §4.3 plus the rules below.
  - `resolve_stage(profile: GuideProfile, level: int | None, override_id: str | None = None) -> GuideStage`: the override wins if the id exists. Otherwise it returns the first `auto` stage whose range contains `level`. With `level=None` it returns the first stage.
- Parsing table (case-insensitive):
  - `lvl|level|lv` + `a-b` → (a, b);
  - `lvl|level` + `n` (e.g. `lvl 52 Swap`, `lvl 85`) → (n, n);
  - bare `a-b` → (a, b);
  - `Act 1`=(1,15), `Act 2`=(16,29), `Act 3`=(30,44), `Act 4`=(45,55), `Interlude`=(56,64);
  - `Act X & Y` → (min of X, max of Y);
  - `Act X to Endgame` → (min of X, 64);
  - keywords `endgame|maps|map|t1..t16|mageblood|dot cap|pinnacle|uber|late|mid|early` (when not covered above) → (65, None, True).
- Assignment rules:
  1. Unparsed stages get `min = previous max + 1`.
  2. For non-keyword stages, `max = next stage's min - 1` when the next stage is a non-keyword stage with a parsed min. Otherwise (next is a keyword stage, or unparsed) it is the stage's own parsed max, or 100 if none. The result must be ≥ min.
  3. Keyword stages: the first gets `min = max(65, previous max + 1)` and `max = 100`, `auto=True`. Later keyword stages get the same range with `auto=False`.
  4. The last auto stage ends at 100.
  5. A single-stage guide is 1–100.

- [ ] **Step 1: Write failing tests**:
  - the parametrized parse table above, including `"Act 1 & 2"`→(1,29), `"Act 4 to Endgame"`→(45,64), `"Early Endgame"`→(65,None,True), `"Random title"`→(None,None,False);
  - Fubgun fixture ranges are exactly `[(1,14),(15,32),(33,51),(52,52),(53,84),(85,85),(86,100),(86,100),(86,100)]` with `auto` `[T,T,T,T,T,T,T,F,F]`;
  - for every fixture and every level 1–100, exactly one auto stage contains the level;
  - `resolve_stage(fubgun, 60).title == "lvl 53-68"`;
  - `resolve_stage(fubgun, 60, override_id=<DoT Cap id>).title == "DoT Cap"`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/builds/test_stages.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `stages.py` and wire it into `parse_mobalytics_guide`.
- [ ] **Step 4: Run** the tests, then `uv run pytest -q`. Expected: green.
- [ ] **Step 5: Commit** — `feat(builds): derive stage level ranges from variant titles`

---

### Task 5: PoB2 share code / pobb.in to GuideProfile

**Files:**
- Create: `companion/builds/pob_code.py`
- Test: `tests/unit/builds/test_pob_code.py`

**Interfaces:**
- Produces:
  - `decode_share_code(code: str) -> str`: strip whitespace, url-safe base64 (pad as needed), `zlib.decompress`, UTF-8. Raises `ValueError("Kode PoB2 tidak valid")`.
  - `fetch_pobb_code(url: str, opener=urllib.request.urlopen) -> str`: accepts only `https://pobb.in/<id>` (with or without `/raw`) and fetches `https://pobb.in/<id>/raw`, timeout 15 s. Anything else raises `ValueError`.
  - `parse_pob_xml(xml: str, name: str) -> GuideProfile`:
    - one stage per `<Items><ItemSet title>`, with `id = ItemSet@id` and title defaulting to `"Set <id>"`;
    - items from `<Slot name itemId>` → `<Item id>` text, mapped to canonical slots (`Weapon 1/2`, `Weapon 1/2 Swap`, `Helmet`, `Body Armour`, `Gloves`, `Boots`, `Amulet`, `Ring 1`, `Ring 2`, `Belt`; jewel/flask slots ignored), with `raw_text` = the item text and `name`/`item_class` taken from the parsed item;
    - `main_skill` from `<Build mainSocketGroup>` indexing the `<Skill>` elements of the active `<SkillSet>`, or of `<Skills>` when there are no skill sets: the first `<Gem nameSpec>` of that skill;
    - `has_pob=True`, `pob_stage_id` = the id of `Items@activeItemSet`.
    The level ranges go through `assign_level_ranges`.

- [ ] **Step 1: Write failing tests**:
  - build a small XML in the test with two ItemSets (`"Leveling lvl 1-40"`, `"Endgame"`), one helmet and one crossbow item and two skills, then `zlib.compress` + urlsafe-b64 it into a code; `decode_share_code(code) == xml`;
  - `parse_pob_xml` gives 2 stages with ranges (1,40)/(65,100), the helmet raw text, `main_skill` and `pob_stage_id`;
  - `decode_share_code("not a code")` raises `ValueError`;
  - `fetch_pobb_code("https://pobb.in/abc", opener=fake)` requests `https://pobb.in/abc/raw`;
  - `fetch_pobb_code("https://evil.com/x")` raises.
- [ ] **Step 2: Run** `uv run pytest tests/unit/builds/test_pob_code.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `pob_code.py`.
- [ ] **Step 4: Run** the tests, then `uv run pytest -q`. Expected: green.
- [ ] **Step 5: Commit** — `feat(builds): import guides from PoB2 share codes and pobb.in`

---

### Task 6: Guide API endpoints

**Files:**
- Modify: `companion/dashboard_api.py` (replace `get_available_guides`; add `import_guide_payload`, `delete_guide_payload`, `update_guide_rules_payload`, `set_character_guide_payload`)
- Modify: `companion/dashboard_server.py` (routes)
- Test: `tests/unit/builds/test_guide_api.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 4, 5.
- Produces:
  - `get_available_guides(runtime_dir: Path, character_id: str | None = None) -> dict` returns `{"guides": [{"slug", "name", "source_url", "has_pob", "stages": [{"id","title","min_level","max_level","auto"}], "breaker_rules": [...]}], "active": {"guide": slug|None, "stage_override": id|None}}`.
  - `import_guide_payload(payload: {"text": str}, runtime_dir) -> dict`. `text` starts with `{` → `parse_mobalytics_guide(json.loads(text))`; a `pobb.in` URL → `fetch_pobb_code` then `parse_pob_xml`; otherwise `decode_share_code` then `parse_pob_xml` with name `"PoB Guide <date>"`. A mobalytics `pob_code` is decoded and stored as XML (a decode failure becomes a warning, not an error). Returns `{"success": True, "slug", "name", "stages": n, "warnings": [...]}` or `{"error": "<Indonesian message>"}`, with nothing written on error.
  - `delete_guide_payload({"slug"})`, `update_guide_rules_payload({"slug", "rules": [...]})` (validates every rule; an invalid regex returns `{"error": "Pola regex tidak valid: ..."}`), `set_character_guide_payload({"character_id", "guide", "stage_override"})`.
  - Routes: `GET /api/guides` (query `char_id`), `POST /api/guides` (import), `POST /api/guides/delete`, `POST /api/guides/rules`, `POST /api/character-guide`.

- [ ] **Step 1: Write failing tests**:
  - importing each fixture (`text = fixture file content`) succeeds and `get_available_guides` lists 3 guides;
  - the Fubgun guide `has_pob` and an XML file exists;
  - import of `"halo"` → error and `runtime/guides` stays empty;
  - truncated JSON → error;
  - JSON with `"format": "other"` → error;
  - an invalid regex rule → error, rules unchanged;
  - `set_character_guide_payload` then `get_available_guides(char)` reports the active guide;
  - an HTTP test through `DashboardRequestHandler` (pattern of `tests/unit/test_dashboard_server_security.py`): `POST /api/guides` with a foreign `Origin` → 403.
- [ ] **Step 2: Run** `uv run pytest tests/unit/builds/test_guide_api.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the functions and routes.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: green.
- [ ] **Step 5: Commit** — `feat(dashboard): guide import/list/delete/rules API`

---

### Task 7: "Tambah Guide" tab and import of the three guides

**Files:**
- Modify: `dashboard/index.html` (new tab in `modal-sync-profile`)
- Create: `dashboard/js/guides.js` (tab logic; imported by `modals.js`)
- Modify: `dashboard/js/modals.js`

**Interfaces:**
- Consumes: Task 6 endpoints, `dashboard/bookmarklet.js`.
- Produces a UI tab "📚 Tambah Guide" with:
  - a textarea and an "Impor Guide" button (`POST /api/guides`), with the result or error shown below;
  - an `<a id="guide-bookmarklet">Salin Guide PoE2</a>` whose `href` is `"javascript:" + encodeURIComponent(<text of /bookmarklet.js>)`, plus the instructions "Seret tombol ini ke bookmark bar, buka halaman guide mobalytics, lalu klik bookmark-nya.";
  - a list of stored guides (name, number of stages, PoB yes/no) with "Hapus" (`POST /api/guides/delete`, after `confirm`).
  All dynamic text goes through `esc()`.

- [ ] **Step 1: Implement the tab.**
- [ ] **Step 2: Verify in the browser pane** against `uv run python -m companion.cli dashboard --port 8091 --no-browser`:
  - paste each fixture file's content and import it;
  - the list shows 3 guides (Fubgun 9 stages with PoB, Navira 8 with PoB, Plant Oracle 1 without PoB);
  - pasting `"halo"` shows the error;
  - the bookmarklet `href` starts with `javascript:`;
  - no console errors.
  Leave the three guides imported in `runtime/guides/`. These are the user's real guides.
- [ ] **Step 3: Run** `uv run pytest -q`. Expected: green.
- [ ] **Step 4: Commit** — `feat(dashboard): Tambah Guide tab with bookmarklet and guide list`
