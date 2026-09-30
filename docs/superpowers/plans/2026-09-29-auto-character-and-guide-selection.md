# Auto-Character Detection & Guide Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Follow strict TDD (test-driven-development). Write failing test FIRST, verify RED, write minimal code, verify GREEN, then refactor.

**Goal:** Provide automated character discovery for account `mikaelzo#5674`, seamless character switching via a dashboard dropdown, and selectable build guides (Fubgun Flameblast vs Generic PoB2 Optimizer) with stage selection without requiring manual typing or manual import clicks.

**Architecture:**
1. **Account Character Auto-Discovery & Switcher (`companion/dashboard_api.py`, `companion/dashboard_server.py`)**:
   - Provide `GET /api/account-characters` which reads character lists from `path-of-building-2-mcp/oauth_status.json` (account `mikaelzo#5674`) and local `runtime/characters/`.
   - Provide `POST /api/select-character` which updates active character, triggers auto-fetch from official PoE2 API / public endpoints if local data is missing/empty, and prepares the PoB2 session cache.
2. **Generic PoB2 Evaluation Mode & Guide Catalog (`companion/dashboard_api.py`)**:
   - Provide `GET /api/guides` listing supported guides: `Fubgun Flameblast Oil Grenade (Mercenary)` and `Generic PoB2 Optimizer (Any Class / Witch / Ranger / Sorceress)`.
   - In `evaluate_item_payload`, when `guide == "generic_pob2"` (or when the character is non-Mercenary and not explicitly pinned to Fubgun), bypass Fubgun-specific constraints (e.g. strict crossbow/staff topologies, flat fire damage build breakers) and evaluate candidates strictly using pure PoB2 Δ DPS and Δ EHP deltas.
3. **Dashboard Header & Controls UI (`dashboard/index.html`, `dashboard/app.js`)**:
   - Replace/augment manual import controls with an intuitive Character Dropdown `<select id="header-char-select">` and quick sync button `🔄 Sync`.
   - Add Guide Selector `<select id="guide-select">` and Stage Selector `<select id="stage-select">`.
   - Automatically populate and select the active character on dashboard load.

**Tech Stack:** Python 3.11+, Pydantic v2, Pytest, Vanilla JS / HTML5 / CSS3.

---

### Task 1: Backend Endpoints for Account Characters & Character Selection

**Problem:** The dashboard currently requires typing the account and character name or manual copy-pasting JSON. It cannot list available characters for `mikaelzo#5674` or switch characters via a single API call.
**Target Behavior:**
- `GET /api/account-characters?account=mikaelzo#5674` returns:
  ```json
  {
    "account": "mikaelzo#5674",
    "characters": [
      {"name": "BOMSHAK", "level": 19, "class": "Mercenary", "league": "Forbidden Rites"},
      {"name": "DaisyofWar", "level": 71, "class": "Witch3", "league": "Standard"},
      {"name": "DespareBlood", "level": 68, "class": "Witch2", "league": "Standard"},
      {"name": "MadDrigo", "level": 32, "class": "Ranger3", "league": "Standard"},
      {"name": "MadDruiud", "level": 41, "class": "Druid2", "league": "Standard"},
      {"name": "Mikaelzo", "level": 33, "class": "Sorceress1", "league": "Standard"},
      {"name": "Mokeied", "level": 40, "class": "Monk1", "league": "Runes of Aldur"}
    ],
    "active_character_id": "BOMSHAK"
  }
  ```
- `POST /api/select-character` with `{"character_id": "DaisyofWar"}`:
  - Updates `runtime/active_character.json` and `runtime/runtime_status.json`.
  - Ensures character profile/loadout exists (or initiates fetch via `fetch_public_profile` / official API).
  - Invalidates and re-seeds PoB2 session for the new character.
  - Returns `{"success": true, "active_character_id": "DaisyofWar"}`.

**Files:**
- Test: `tests/unit/test_dashboard_api.py`
- Modify: `companion/dashboard_api.py`
- Modify: `companion/dashboard_server.py`

- [ ] **Step 1: Write failing tests in `tests/unit/test_dashboard_api.py`**
  - Test `get_account_characters()` returns list of characters from OAuth/local files for `mikaelzo#5674`.
  - Test `select_character_payload()` sets active character and invalidates PoB session.
- [ ] **Step 2: Run test to verify RED**
  - `uv run pytest tests/unit/test_dashboard_api.py::test_get_account_characters -v`
- [ ] **Step 3: Implement `get_account_characters` and `select_character_payload` in `companion/dashboard_api.py` and register routes in `companion/dashboard_server.py`**
- [ ] **Step 4: Run test to verify GREEN**
  - `uv run pytest tests/unit/test_dashboard_api.py -k "account_characters or select_character" -v`

---

### Task 2: Build Guide Catalog & Generic PoB2 Evaluation Mode

**Problem:** Currently, `evaluate_item_payload` assumes the Fubgun Flameblast build for all evaluations. If the user selects `DaisyofWar` (Witch) or `Mikaelzo` (Sorceress), Fubgun's weapon router and fire-damage rules inappropriately reject items.
**Target Behavior:**
- Add `GET /api/guides` returning:
  ```json
  {
    "guides": [
      {
        "id": "fubgun_flameblast",
        "name": "Fubgun Flameblast Oil Grenade",
        "class": "Mercenary",
        "stages": ["auto", "lvl 1-14", "lvl 15-32", "lvl 33-51", "lvl 52 swap", "lvl 53-68", "lvl 85", "endgame", "mageblood", "dot cap"]
      },
      {
        "id": "generic_pob2",
        "name": "Generic PoB2 Optimizer (Any Class)",
        "class": "Any",
        "stages": ["auto"]
      }
    ]
  }
  ```
- In `evaluate_item_payload`:
  - Accept optional `guide` parameter (default: auto-detected, `"fubgun_flameblast"` if Mercenary, `"generic_pob2"` otherwise).
  - In `generic_pob2` mode: evaluate items purely by PoB2 simulation metrics (Δ DPS, Δ EHP, Δ Resistances, Δ Life) and standard requirements without Fubgun-specific weapon routing or flat fire damage build-breakers.

**Files:**
- Test: `tests/unit/test_dashboard_api.py`
- Modify: `companion/dashboard_api.py`
- Modify: `companion/dashboard_server.py`

- [ ] **Step 1: Write failing tests in `tests/unit/test_dashboard_api.py`**
  - Test `test_get_available_guides()`
  - Test `test_evaluate_item_payload_generic_pob2_allows_wand_or_staff_without_fubgun_rejection()`
- [ ] **Step 2: Run test to verify RED**
  - `uv run pytest tests/unit/test_dashboard_api.py::test_get_available_guides -v`
- [ ] **Step 3: Implement guide catalog and generic PoB2 evaluation mode in `companion/dashboard_api.py`**
- [ ] **Step 4: Run test to verify GREEN**
  - `uv run pytest tests/unit/test_dashboard_api.py -k "guides or generic_pob2" -v`

---

### Task 3: Dashboard Frontend Header UI with Auto-detection, Character Dropdown, Guide Dropdown, & Stage Selector

**Problem:** Dashboard UI has a static character chip and requires opening a modal to type or paste JSON.
**Target Behavior:**
- Replace `#char-chip` with an interactive Character Selector dropdown (`#header-char-select`) that lists all characters for `mikaelzo#5674`.
- Add a quick sync button (`🔄 Sync`) beside the dropdown to immediately refresh gear from GGG.
- In sidebar / controls, add a Guide Selector dropdown (`#guide-select`) and Stage Selector dropdown (`#stage-select`).
- When a user changes the character in the dropdown:
  - Call `/api/select-character`.
  - Automatically update the selected guide (e.g. switch to Generic PoB2 if Witch/Sorceress, or Fubgun if Mercenary).
  - Refresh the dashboard state, equipment slots, baseline stats, and active PoB2 session.
- When an item is evaluated via auto-clipboard, pass the active `guide` and `stage` parameters.

**Files:**
- Modify: `dashboard/index.html`
- Modify: `dashboard/app.js`
- Modify: `dashboard/style.css`

- [ ] **Step 1: Update `dashboard/index.html` with Character Dropdown, Guide Selector, and Stage Selector elements**
- [ ] **Step 2: Add styles in `dashboard/style.css` for clean dropdown styling matching the dark fantasy theme**
- [ ] **Step 3: Update `dashboard/app.js` to fetch `/api/account-characters` on startup, populate dropdowns, handle character/guide switching, and pass them to evaluation requests**
- [ ] **Step 4: Verify dashboard CLI and endpoints pass tests**
  - `uv run pytest tests/cli/test_dashboard_cli.py -v`

---

### Task 4: Full System Verification and Regression Testing

- [ ] **Step 1: Run complete test suite**
  - `uv run pytest`
  - Verify all 1818+ tests pass with 0 regressions.
- [ ] **Step 2: Verify dashboard server launch and auto-discovery**
  - Test server responses using Python HTTP client probe.
