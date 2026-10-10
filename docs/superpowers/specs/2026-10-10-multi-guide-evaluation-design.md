# Multi-Guide Item Evaluation & MCP Import Hardening — Design

**Date:** 2026-10-10
**Status:** Draft, awaiting user review
**Supersedes:** `2026-09-25-modular-weapon-subsystems.md` (the `FubgunWeaponProfileRouter` part; `WeaponTopologyResolver` is kept)
**Inputs:** `docs/audits/2026-10-10-COMPARE_AND_MCP_IMPORT_AUDIT.md` (findings #1–#18)

---

## 1. Goal

Item comparison must work for any build guide the user picks, not only Fubgun Flameblast. At the same time, the audit findings should be fixed from the bottom up: engine and character data first, then guides, then evaluation, then UI.

The user wants to keep several guides at once. The first three are:
- https://mobalytics.gg/poe-2/builds/fubgun-flameblast-oil-grenade (9 variants, PoB code = final build only)
- https://mobalytics.gg/poe-2/builds/naviras-fracturing-varashta-league-starter (8 variants, PoB code)
- https://mobalytics.gg/poe-2/builds/plant-oracle-druid-leveling-build-guide (1 variant, no PoB code)

**Success criteria**
- Each character can have a different active guide, and switching guides changes stages, priorities and breaker rules without code changes.
- One evaluation pipeline serves the dashboard (manual and auto-scan) and the CLI watcher. The same item and character produce the same verdict no matter how the item arrived.
- A guide's breaker rule vetoes on every engine path (the audit probe "gloves with fire-to-attacks at lvl 53" returns REJECT).
- No orphaned PoB2 Docker engines, and "current" items carry full item text.

**Non-goals**
- Fetching mobalytics server-side. Their pages return HTTP 403 to non-browser clients, and we do not work around that.
- An offense model for the heuristic (no-PoB2) path.
- Multi-user or LAN use. This is a personal tool.

## 2. Decisions taken during brainstorming

| Topic | Decision |
|---|---|
| Guide source | Mobalytics variant data, copied by a user-run bookmarklet; PoB2 share code / pobb.in as a secondary source |
| Guide roles in evaluation | Stages (from variants), stat priorities from the guide's gear, simulation in the guide build |
| Damage skill for the character simulation | The character's own main skill (from its PoB2 import), not the guide's |
| Build-breakers | Optional per-guide rule list; Fubgun's early-ignite rule is the first entry |
| Architecture | Approach A: one guide profile model plus one generic policy; Fubgun-specific code retired |
| Import UX | Bookmarklet copies JSON, which the user pastes into the dashboard |

## 3. Architecture

```
companion/builds/                    NEW — knows guides, nothing about PoB engine or verdicts
  guide.py        GuideProfile, GuideStage, StageItem, BreakerRule (pydantic)
  mobalytics.py   parse bookmarklet JSON ("poe2-companion-guide/1") -> GuideProfile
  pob_code.py     parse PoB2 share code / pobb.in raw -> GuideProfile (stages = ItemSets)
  stages.py       level ranges from titles; resolve active stage for a character level
  priorities.py   must-have / priority mods per slot for a stage
  store.py        runtime/guides/<slug>.json (+ <slug>.xml); per-character active guide
dashboard/bookmarklet.js             NEW — source of the bookmarklet (served for copy)

companion/equipment/
  evaluation.py   NEW — the only place the evaluation order lives
  safety.py       NEW — applies GuideProfile.breaker_rules (replaces fubgun_rules + build_breaker wiring)
  policy.py       NEW — generic relative-threshold policy (replaces fubgun_priorities)
  slot_resolver.py NEW — server-side target slot(s) from item class + guide stage weapons,
                  built on the existing build-agnostic weapon_topology.py
  pob2_equipment_advisor.py  one simulation helper for all slots; lifecycle fixes
  tactical_advisor.py        zone/resistance veto only (Fubgun text removed)
  api_adapter.py             import fidelity fixes
companion/dashboard_api.py   thin: HTTP payload -> evaluation.evaluate(...)
```

**Dependency direction:** `evaluation` → (`builds`, `safety`, `slot_resolver`, `pob2_equipment_advisor`, `policy`, `tactical_advisor`). Nothing depends on `dashboard_api`. `builds` depends only on the item parser.

**Retired after phase 4:** `fubgun_priorities.py`, `fubgun_weapon_router.py`, `fubgun_rules.py`, `pob2_helmet_advisor.py`, `weapon_projection.py`, the `_STAGE_MAP` in `dashboard_api.py`, `GUIDE_STAGES_MAP` in `dashboard/js/controls.js`, the hardcoded guide list in `get_available_guides`. `BuildProgressionStage` is no longer used by the new pipeline. It is removed once no caller remains.

## 4. Guide model and import

### 4.1 Bookmarklet

The bookmarklet runs on a mobalytics build page in the user's browser. It reads `window.__PRELOADED_STATE__`, locates the document at `poe2State.apollo.graphqlV2.queries[*].state.data[0].game.documents.userGeneratedDocumentBySlug.data`, and copies this JSON to the clipboard:

```json
{
  "format": "poe2-companion-guide/1",
  "source_url": "https://mobalytics.gg/poe-2/builds/<slug>",
  "name": "<data.name>",
  "pob_code": "<data.data.pobCode or null>",
  "variants": [
    {"id": "1", "title": "lvl 15-32",
     "equipment": { ...buildVariants.values[i].equipment... },
     "skill_gems": { ...buildVariants.values[i].skillGems... }}
  ]
}
```

Variant titles come from `data.content[*].data.childrenVariants[*]` (`{id, title}`), joined to `data.data.buildVariants.values[*]` by `id`. The bookmarklet makes no network requests. If the expected paths are missing, it shows `alert("Format halaman tidak dikenal")` and copies nothing.

### 4.2 Profile

```python
class StageItem:       # one guide item for one slot in one stage
    slot: str                    # canonical PoB slot: "Helmet", "Weapon 1", "Weapon 1 Swap", ...
    base_name: str
    item_class: str              # from itemClassSlug, e.g. "crossbow", "boots"
    base_stats: dict[str, str]   # "Armour": "74"
    mods: list[str]              # explicitDescriptions[].description
    must_have: list[str]         # mods flagged mustHave
    raw_text: str                # synthesized PoE clipboard text (for parsing / simulation)

class BreakerRule:
    pattern: str                 # case-insensitive regex over a single mod line
    from_level: int = 1
    exclude_slots: list[str] = []
    reason: str

class GuideStage:
    id: str; title: str
    min_level: int; max_level: int
    items: dict[str, StageItem]
    main_skill: str | None       # first active gem name
    weapon_classes: dict[int, set[str]]   # {1: {"staff"}, 2: {"crossbow"}}

class GuideProfile:
    slug: str; name: str; source_url: str | None; imported_at: datetime
    stages: list[GuideStage]
    pob_xml_path: str | None     # set when pob_code decoded successfully
    pob_stage_id: str | None     # stage the PoB build represents (last stage by default)
    breaker_rules: list[BreakerRule]
```

Mobalytics equipment keys map to canonical slots: `helmet, body, gloves, boots, amulet, belt, leftRing→Ring 1, rightRing→Ring 2, mainHand.set1→Weapon 1, offHand.set1→Weapon 2, mainHand.set2→Weapon 1 Swap, offHand.set2→Weapon 2 Swap`. Flasks, charms and `extraRing` are ignored.

### 4.3 Stage level ranges (`stages.py`)

Ranges are parsed from titles in this order:
1. Explicit numbers: `lvl 33-51` → 33–51, `lvl 52 Swap` / `level 52` → 52–52, `lvl 85` → 85–85.
2. Acts, using an approximate PoE2 table: `Act 1` 1–15, `Act 2` 16–29, `Act 3` 30–44, `Act 4` 45–55, `Interlude` 56–64.
3. Keywords: `Endgame`, `Maps`, `T1`–`T16`, `Mageblood`, `DoT Cap`, `Pinnacle`, `Uber`, `Late`/`Mid`/`Early Endgame` → ≥ 65, in title order.

Unparsed stages take the gap between their neighbours. Stages are then made contiguous: each `max_level` becomes the next stage's `min_level - 1`, and the last stage gets 100. Overlapping endgame stages (e.g. `Endgame`, `Mageblood`, `DoT Cap`) are reachable only through a manual override. Auto picks the first stage whose range contains the level. A guide with one stage covers 1–100.

**Effective character level** = max(level in `runtime/characters/<id>.json`, PoB2 session level).

### 4.4 PoB2 share code / pobb.in (secondary)

The share code is decoded with `pob_mcp.share_code.decode_share_code`, or with a local copy of the same three steps (url-safe base64 → zlib → XML) when the MCP repository is absent. Each `<ItemSet>` becomes a stage, with items taken from `<Item>` text. Skill sets are matched to item sets by title, then by position, then the active one. pobb.in input fetches `https://pobb.in/<id>/raw`. When a mobalytics JSON includes `pob_code`, the decoded XML is stored next to the profile and `pob_stage_id` is the last stage.

### 4.5 Storage and selection

- `runtime/guides/<slug>.json` and the optional `runtime/guides/<slug>.xml`.
- Re-import overwrites the stored stages and keeps `breaker_rules`.
- The active guide is stored per character as `active_guide` (and optionally `stage_override`) in `runtime/characters/<id>.json`.
- When the active guide is deleted, the character falls back to "character only" mode.
- No guide selected ("character only" mode): one implicit stage 1–100, no items, no rules.

## 5. Evaluation pipeline (`evaluation.py`)

```python
def evaluate(raw_text, character_id, *, runtime_dir, pob_session, source: Literal["manual", "auto", "cli"],
             locked_slot: str | None = None, zone: str | None = None,
             stage_override: str | None = None) -> EvaluationResult
```

1. **Context.** Parse the candidate, load the character, the active guide and the effective level, then resolve the stage (override or auto).
2. **Slot resolution** (`slot_resolver.py`). The item class gives the slot family.
   - Weapons: the weapon set is the one whose stage `weapon_classes` contains the candidate class. If both or neither match, both sets are candidates. 1H weapons are tried in both hands of the chosen set.
   - Rings: both ring slots.
   - `locked_slot` restricts this to one slot.
   - Topology (2H clears the off-hand, bow+quiver) comes from `weapon_topology.py`.
3. **Safety gate** (`safety.py`). Each mod line of the candidate is matched against the guide's `breaker_rules` where `level ≥ from_level` and the target slot is not in `exclude_slots`. Any match → REJECT with the rule reason. A weapon whose class appears in no stage of the guide → REJECT ("senjata tidak dipakai guide"). This gate runs before and regardless of the engine.
4. **Character simulation.** For each candidate slot, `Pob2EquipmentSession.measure(slot, raw)` returns before/after for that slot (§6). Without PoB2, a heuristic projection gives the same delta shape for non-weapons and `INSUFFICIENT_DATA` for weapons.
5. **Policy** (`policy.py`), on relative deltas: `dps_pct = Δdps / max(dps_before, 1)` and `ehp_pct = Δehp / max(ehp_before, 1)`.
   - `EQUIP_NOW`: (`dps_pct ≥ +1%` and `ehp_pct ≥ −1%`) or (`ehp_pct ≥ +2%` and `dps_pct ≥ −0.5%`), and no resistance newly below its cap, and requirements met.
   - `REJECT`: (`dps_pct ≤ −1%` and `ehp_pct ≤ 0`), or a resistance newly below cap with no DPS/EHP gain, or requirements not met.
   - Otherwise `CONDITIONAL_UPGRADE` with trade-off text.
   - Guide priorities: if the stage item for this slot has `must_have` mods the candidate lacks, the verdict is capped at `CONDITIONAL_UPGRADE`. `priority_match = matched / total` over that stage item's mods, using normalized mod families from the existing normalizer.
   - The thresholds are module constants, to be calibrated against real items after phase 2.
6. **Multi-slot choice.** Among candidate slots, an empty slot with a non-REJECT verdict wins. Otherwise the best verdict wins, ties broken by `dps_pct` then `ehp_pct`. All per-slot results are returned.
7. **Guide-build simulation** (phase 4, only when `pob_xml_path` exists and the active stage is `pob_stage_id`): the candidate is equipped in the guide XML in place of the guide's item, giving `target_fit {dps_pct, ehp_pct}`. This is informational and never changes the verdict.
8. **Tactical veto.** `generate_tactical_advice` (zone/resistance) is merged with `merge_verdicts`, which can only lower the verdict.

```python
class EvaluationResult:
    verdict: Literal["EQUIP_NOW", "CONDITIONAL_UPGRADE", "REJECT", "INSUFFICIENT_DATA", "ALREADY_EQUIPPED"]
    engine: Literal["pob2", "heuristic"]
    engine_reason: str | None          # why not pob2
    slot: str                          # chosen canonical slot (UI must use it)
    slot_reason: str
    per_slot: list[SlotResult]         # verdict + dims per tried slot
    dims: dict[str, float]             # dps_pct, ehp_pct, life, fire_res, ...
    guide: GuideSignal | None          # name, stage title, priority_match, must_have_missing, target_fit
    safety: list[str]                  # triggered rule reasons
    reasons: list[str]; trade_offs: list[str]; gains: list[str]
    tactical_advice: dict | None
    current_item_name: str | None; item_name: str; base_type: str
```

`dashboard_api` keeps its existing response keys (`verdict`, `slot`, `gains`, `trade_offs`, `reason`, `tactical_advice`, `engine`, ...) by flattening `EvaluationResult`, so the UI can migrate in phase 3.

## 6. PoB2 session changes (`pob2_equipment_advisor.py`)

- **One measurement helper**, `measure(slot, raw, candidate_id)`, used by every slot type:
  1. Import the baseline XML into the sandbox with `useSecondWeaponSet` set for `* Swap` slots.
  2. Apply topology `clear_slots` if needed.
  3. `set_main_skill(character_main_group)`, then measure before.
  4. Equip the candidate and re-lock the skill, then measure after.
  5. Restore the sandbox in `finally`.
  `simulate_item`, `simulate_ring_candidate`, `simulate_ambiguous_1h_weapon` and `simulate_weapon_plan` become thin wrappers or are removed (fixes #6, #7, #8).
- `character_main_group` is the imported character's `mainSocketGroup`, resolved once per import. The Fubgun skill-name list in `get_primary_socket_group` is removed.
- **Staleness per source:** `submit_candidate(source)` keeps a separate counter per `source`, so manual and auto-scan no longer cancel each other (#16).
- **Lifecycle:**
  - `close()` runs on failed `initialize()` after engines start.
  - `invalidate_pob_session` calls `sync_character()` and keeps the session.
  - Replaced or unavailable sessions are closed (#3).
- **Refresh:** a background `sync_character()` runs when effective level or zone changes, or when the last sync is more than 10 minutes old. `session.level` is updated by every sync (#9).
- `get_equipped(slot).raw` becomes the source of "current item" text for evaluation and for the loadout file (#4).

## 7. Import pipeline fixes (phase 0)

- **`api_adapter.parse_character_payload`:**
  - Strip markup from property names with the same regexes as `pob_mcp.poe_api._clean_mod`, and write all properties.
  - Include `requirements`, `ilvl`, `desecratedMods` and `mutatedMods`.
  - Write the correct `Item Class` (from the API's inventory/category) and use `baseType` for the base.
  - When a PoB2 session is available after import, replace each slot's `raw_text` with `get_equipped(slot).raw`.
- **Baseline from PoB2:** life, effective resistances, armour/evasion/ES and attributes are filled from `get_defenses` / `calc_stats`. Facts with source `MANUAL_USER_INPUT` are preserved and every other fact is overwritten.
- **Ghost slots:** an official import (`overwrite=True`) starts gear slots from empty instead of copying the previous loadout.
- **Account characters:** `get_account_characters` calls `pob_mcp.poe_api.list_characters()` when a token is valid (cached 5 min) and merges in local files. The fake `BOMSHAK lvl 19` fallback and the `oauth_status.json` read are removed.
- **`fetch_public_profile`:** when the MCP backend exists, the `PoEApiError` / `OAuthError` message is returned. The legacy `character-window` fallback and its Chrome User-Agent are removed.

## 8. UI (phase 3)

- **Sidebar:** the guide dropdown lists stored guides plus "Karakter saja". The stage dropdown shows "Auto" plus the guide's stage titles. Both are saved per character via a new `POST /api/character-guide`.
- **"Tambah Guide" tab** in the import modal:
  - paste box (bookmarklet JSON or PoB code / pobb.in link),
  - the bookmarklet's `javascript:` URL with install steps,
  - stored guides with re-import/delete,
  - a breaker-rule editor.
  New endpoints: `GET /api/guides`, `POST /api/guides`, `DELETE /api/guides/<slug>`, `PUT /api/guides/<slug>/rules`.
- **Verdict card:**
  - server `slot` and `slot_reason`,
  - `dps_pct` / `ehp_pct` formatted as percentages,
  - "Prioritas guide 3/4 (kurang: Movement Speed)",
  - "Di build target: …" when present,
  - a safety badge with the rule reason,
  - `engine_reason` when heuristic.
- **Manual compare** sends no slot unless "Kunci slot" is checked. **Auto-scan** uses the server `slot` / `recommended_slot` and never overwrites it.
- **Auto-equip to empty slot** only when `verdict == "EQUIP_NOW"` and the server reports the slot empty (#11).
- **Header** shows PoB2 `unavailable_reason` when the engine is unavailable.

## 9. Error handling

- **Guide import:** validation errors list the missing path or field. Nothing is written unless the whole profile validates.
- **PoB2 unavailable or simulation exception:** heuristic result with `engine_reason`, plus a logged warning or exception. No `except: pass` on the evaluation path.
- **OAuth/API:** errors are surfaced verbatim to the UI.
- **Missing guide data for a slot** (e.g. Plant Oracle without a Set 2 weapon): no priority signal for that slot, and the verdict comes from policy alone.

## 10. Testing

- **`builds/`:**
  - parser tests on bookmarklet JSON fixtures recorded from the three mobalytics pages (stored under `tests/fixtures/guides/`),
  - stage-range parsing tables,
  - effective-level resolution,
  - PoB code decode with a small XML fixture.
- **`safety.py`:** the audit probe (fire-to-attacks gloves, lvl 53, Fubgun guide) returns REJECT for both the pob2 and heuristic engines, and the same item with a Navira guide is not vetoed by the Fubgun rule.
- **`policy.py`:** table tests for the relative thresholds, resist-cap breach and the must-have cap.
- **`slot_resolver.py`:** Fubgun lvl 60 crossbow → Set 2, staff → Set 1, 1H → both hands, ring → both rings, locked slot respected.
- **`pob2_equipment_advisor`:** with the mock engine, `measure` toggles `useSecondWeaponSet` for swap slots, locks the main skill before and after, and restores the sandbox. Closing on invalidate and on failed init.
- **`evaluation.py`:** manual and auto sources give identical results for the same item. Tactical cannot promote.
- **Migration:** behavioural tests from the retired Fubgun modules (~112 tests in coupled files) are rewritten against `evaluation.evaluate` with a Fubgun guide fixture. Tests of retired internals are deleted.
- **Live check after phase 2:** one real Set 2 crossbow comparison and one ring comparison with the PoB2 engine running.

## 11. Phases

| Phase | Scope | Audit findings |
|---|---|---|
| 0 | Session lifecycle, refresh, import fidelity, baseline from PoB2, character list, OAuth errors | #3 #4 #9 #12 #13 #14 |
| 1 | `companion/builds/`, bookmarklet, guide store, import of the 3 guides by the user | — |
| 2 | `evaluation.py`, `safety.py`, `policy.py`, `slot_resolver.py`, `measure()` helper, Fubgun as guide, test migration | #1 #2 #5 #6 #7 #8 #10 #15 #16 #17 |
| 3 | Dashboard UI for guides, verdict card, slot lock, auto-equip rule | #5 (UI) #11 #18 |
| 4 | Guide-build simulation, retire old modules, CLI watcher on `evaluation.evaluate` | — |

Each phase ends with a green test suite and a working dashboard.

**Test fixtures** for the three guides are captured during phase 1 by running the bookmarklet's extraction code in the built-in browser pane on the pages the user linked. This is ordinary page viewing with no automated server-side fetching. Phase 2's Fubgun fixture comes from the same capture.

**User action in phase 1:** install the bookmarklet once. Later guides (and re-imports of these three) go through it.
