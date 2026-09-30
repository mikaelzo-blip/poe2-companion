# Zone-Aware Tactical & Decisive Equipment Advisor Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Follow strict TDD (test-driven-development). Write failing test FIRST, verify RED, write minimal code, verify GREEN, then refactor.

**Goal:** Transform the PoE2 Companion Equipment Advisor from a passive/indecisive rule evaluator into a bold, zone-aware tactical advisor that understands current zone threats, upcoming boss encounters, sustain/regen trade-offs, and attribute requirements, delivering decisive verdicts instead of sitting on the fence.

**Architecture:**
1. **Decisive Policy Hardening (`fubgun_priorities.py`)**:
   Eliminate false `CONDITIONAL_UPGRADE` verdicts when an item incurs net defensive/resistance regressions and negative EHP despite secondary local defense gains (e.g., +82 Armour but -7 Life, -15% Fire Res, -4% Lightning Res, -16.80 EHP must evaluate to `REJECT / KEEP CURRENT`).
2. **Zone Threat & Encounter Matrix (`zone_threats.py`)**:
   Model PoE2 zone IDs (`G2_1`, `G1_*`, etc.) and named zones to their Act, lethal damage types (Fire, Cold, Lightning, Physical, Chaos), key encounter/boss mechanics, and recommended resistance baselines.
3. **Tactical Equipment Intelligence (`tactical_advisor.py`)**:
   Synthesize PoB2 metrics, zone threats, sustain affixes (Life Regen/sec), and attribute penalties into a structured tactical briefing (`TacticalAdvice`) with actionable recommendations ("Tahan gear lama", "Simpan di tas untuk farming", "Ganti sekarang").
4. **Dashboard API & UI Integration (`dashboard_api.py`, `dashboard/app.js`)**:
   Deliver tactical analysis to the dashboard UI with dedicated badges, zone threat warnings, sustain evaluations, and decisive action guides.

**Tech Stack:** Python 3.11+, Pydantic v2, Pytest, Vanilla JS / CSS.

---

### Task 1: Decisive Policy Hardening against Net Defense Regressions

**Problem:** When a candidate has `armour_delta > 20` but causes negative Life, negative resistances, and negative EHP, `evaluate_fubgun_equipment_policy` currently awards `CONDITIONAL_UPGRADE` via `secondary_gain`, confusing the player.
**Target Behavior:** If `ehp_delta < -5.0` or (`life_delta <= 0` and total resistance delta < 0 and `ehp_delta < 0`), a secondary local defense gain does NOT warrant `CONDITIONAL_UPGRADE`. It must be decisively evaluated as `REJECT / KEEP CURRENT`.

**Files:**
- Test: `tests/unit/equipment/test_decisive_advisor.py`
- Modify: `companion/equipment/fubgun_priorities.py`

- [x] **Step 1: Write failing test in `tests/unit/equipment/test_decisive_advisor.py`**
  Add `test_maelstrom_keep_vs_glyph_pelt_is_decisively_rejected_due_to_heavy_res_and_ehp_loss()` testing that +82 Armour with -7 Life, -15% Fire Res, -4% Lightning Res, and -16.80 EHP yields `Verdict.REJECT`.
- [x] **Step 2: Run test to verify RED**
  `uv run pytest tests/unit/equipment/test_decisive_advisor.py::test_maelstrom_keep_vs_glyph_pelt_is_decisively_rejected_due_to_heavy_res_and_ehp_loss -v`
- [x] **Step 3: Implement minimal fix in `fubgun_priorities.py`**
  Ensure negative EHP or combined primary losses block `secondary_gain` promotion to `CONDITIONAL_UPGRADE` and route to `REJECT`.
- [x] **Step 4: Run test to verify GREEN**
  `uv run pytest tests/unit/equipment/test_decisive_advisor.py -v`

---

### Task 2: Zone & Encounter Threat Matrix (`zone_threats.py`)

**Problem:** The system reads `Zone: G2_1` from game client logs, but the advisor is blind to what threats exist in that zone or what bosses are coming up.
**Target Behavior:** Implement `ZoneThreatMatrix` with lookup by zone ID (`G2_1`, `G1_1`, etc.) or zone name, returning:
- Act and friendly zone name (e.g. `G2_1` -> `Act 2: Vastiri Outskirts / Caravan`)
- Dangerous damage types (e.g. `["Fire", "Physical"]`)
- Recommended resistance minimums for the zone (e.g. `Fire: 35%`)
- Upcoming boss / encounter threats (e.g. `The Dreadnought`, `Jamanra / Vastiri Bandits`)
- Tactical survival notes.

**Files:**
- Create: `companion/equipment/zone_threats.py`
- Create: `tests/unit/equipment/test_zone_threats.py`

- [x] **Step 1: Write failing tests in `tests/unit/equipment/test_zone_threats.py`**
  Test lookup for `G2_1`, `G1_11`, unknown zones, and default campaign fallbacks.
- [x] **Step 2: Run test to verify RED**
  `uv run pytest tests/unit/equipment/test_zone_threats.py -v`
- [x] **Step 3: Implement `ZoneThreatMatrix` and `ZoneThreatProfile` in `companion/equipment/zone_threats.py`**
- [x] **Step 4: Run test to verify GREEN**
  `uv run pytest tests/unit/equipment/test_zone_threats.py -v`

---

### Task 3: Tactical Advisor Module (`tactical_advisor.py`)

**Problem:** Player needs human-like, decisive analysis covering:
1. Zone-specific danger checks (e.g. losing Fire Res in a Fire-heavy Act 2 zone is lethal).
2. Attribute loss risks (e.g. losing +12 Strength might disable gems).
3. Sustain value (e.g. +5.8 Life Regen/sec is high-tier sustain for Act 2).
4. Direct, actionable decision: "Tahan gear saat ini", "Kapan boleh dipakai", "Simpan di stash".

**Files:**
- Create: `companion/equipment/tactical_advisor.py`
- Create: `tests/unit/equipment/test_tactical_advisor.py`

- [x] **Step 1: Write failing tests in `tests/unit/equipment/test_tactical_advisor.py`**
  Test generating decisive tactical advice for:
  - Case A: Maelström Keep in `G2_1` (rejects due to lethal fire res loss in Act 2 Vastiri, notes 5.8 regen sustain potential for stash, warns about STR loss).
  - Case B: Clean upgrade in dangerous zone.
  - Case C: Pure physical zone where armor swap is acceptable.
- [x] **Step 2: Run test to verify RED**
  `uv run pytest tests/unit/equipment/test_tactical_advisor.py -v`
- [x] **Step 3: Implement `generate_tactical_advice` in `companion/equipment/tactical_advisor.py`**
- [x] **Step 4: Run test to verify GREEN**
  `uv run pytest tests/unit/equipment/test_tactical_advisor.py -v`

---

### Task 4: Dashboard API & Server Integration

**Problem:** Dashboard API currently evaluates items in isolation without passing character zone, and does not return the tactical analysis card.

**Files:**
- Test: `tests/unit/test_dashboard_api.py`
- Modify: `companion/dashboard_api.py`

- [x] **Step 1: Write failing tests in `tests/unit/test_dashboard_api.py`**
  Verify `evaluate_item_payload` accepts `zone` (or resolves it from character state `G2_1`), invokes tactical advisor, and returns `tactical_advice` dictionary.
- [x] **Step 2: Run test to verify RED**
  `uv run pytest tests/unit/test_dashboard_api.py -k test_tactical_advice -v`
- [x] **Step 3: Integrate tactical advisor into `companion/dashboard_api.py`**
- [x] **Step 4: Run test to verify GREEN**
  `uv run pytest tests/unit/test_dashboard_api.py -v`

---

### Task 5: Dashboard UI Presentation (`dashboard/app.js`, `dashboard/style.css`)

**Problem:** The dashboard UI only shows generic raw strings. It needs a high-visibility Tactical Briefing Card showing:
- 📍 **Konteks Zona & Lawan** (Ancaman spesifik Act 2 / Boss)
- ⚠️ **Audit Atribut & Sustain** (+5.8 Regen/s, Resiko defisit Strength)
- 🛡️ **Keputusan Taktis Berani** (Rekomendasi tegas & saran stash/simpan)

**Files:**
- Modify: `dashboard/app.js`
- Modify: `dashboard/style.css`

- [x] **Step 1: Update `dashboard/app.js` to render the Tactical Briefing Card**
- [x] **Step 2: Add styles in `dashboard/style.css` for tactical card, warning badges, and zone threat tags**
- [x] **Step 3: Verify end-to-end with unit/integration tests and browser check**
