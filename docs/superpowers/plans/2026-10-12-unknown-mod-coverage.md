# Unknown Modifier Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the modifier-normalizer gaps that change production results, instead of growing the type dictionary for its own sake.

**Architecture:** Production reads `NormalizedModifierType` in two places only: guide priority matching (`companion/builds/priorities.py::mod_family`, which already falls back to a number-free text family for UNKNOWN lines) and the no-PoB heuristic projection (`companion/equipment/contribution.py`: life, four resistances, three attributes, movement speed). So the fixes are: (1) all-res / all-attributes lines that were defined as regexes but never wired, so the heuristic projection drops them; (2) clipboard tags such as `(implicit)` and `(rune)` that leak into the text family, so a candidate's implicit never matches the guide's wanted mod; (3) PoE2 wording that the PoE1-era regexes miss.

**Tech Stack:** Python 3.11, pydantic, pytest (`uv run pytest`).

**Spec:** this plan plus the analysis below (no separate spec). Carry-over origin: `.superpowers/sdd/2026-10-10-phase1-guide-model/progress.md` line 43.

## Analysis (2026-10-12, scan of runtime guides + user loadouts)

352 of 697 mod lines (50%) parse as UNKNOWN_MODIFIER (Fubgun 44%, Navira 52%, Plant 34%, user items 61%). Most frequent families: `# to Level of all Minion Skills` 28, `# to maximum Energy Shield` 28, `# to maximum Mana` 24, `#% increased Rarity of Items found` 23, `Adds # to # Physical Damage to Attacks` 13, `# to Spirit` 13, `#% increased Spell Damage` 10, `# Life Regeneration per second` 10; 85 distinct families in total.

Most of these have no consumer: priority matching already handles them through the text family, and the heuristic projection has no mana/spirit/minion dimension (PoB2 is the primary engine and does not use the normalizer). Adding enum values for them would only move the percentage. The lines that do change results:

- `#% to all Elemental Resistances` (6) and `# to all Attributes`: `RE_ALL_RES` / `RE_ALL_ATTR` exist in `normalizer.py` but are never used, so the heuristic projection counts 0 resistance / 0 attributes for them.
- `... (implicit)` / `(rune)` suffix: `mod_family("Adds 1 to 4 Physical Damage to Attacks (implicit)")` returns `adds # to # physical damage to attacks (implicit)`, which never equals the guide's family.
- PoE2 wording missed by typed regexes: `Gain #% of Damage as Extra Fire Damage` (regex wants "Physical Damage"), `+# to Level of all Fire Spell Skills` / `all Spell Skills` (regex wants "Skill Gems"), `+# to maximum Energy Shield` (regex wants "to Energy Shield").

## Global Constraints

- Keep accepting the old wordings already pinned by tests (`Skill Gems`, `of Physical Damage as Extra Fire`, `to Energy Shield`).
- No new dependency. No change to PoB2 code paths.
- Existing stored items keep their old modifier types until re-imported; a re-import of the same item now parses more known mods and replaces the stored copy once (expected, see `session_import._apply_items`).

## Review Focus

- Advanced-copy ranges: `+12(10-15)% to all Elemental Resistances` must give value 12 (Task 1 test).
- Conditional all-res (`... while on Full Energy Shield`) must stay CONDITIONAL and not count in contribution (Task 1 test).
- Tagged typed mods: `+20% to Fire Resistance (rune)` keeps FIRE_RESISTANCE (Task 1 test).
- Jewellery flat ES: `+30 to maximum Energy Shield` with `slot=SlotType.RING` stays non-local (Task 1 test asserts it is not LOCAL_ENERGY_SHIELD).
- Tag stripping must not eat real text in parentheses that is not a tag, e.g. `(30-50)` ranges (Task 2 test).

---

### Task 1: Normalizer wording, all-res / all-attributes types, contribution

**Files:**
- Modify: `companion/equipment/schema.py` (`NormalizedModifierType`)
- Modify: `companion/equipment/normalizer.py`
- Modify: `companion/equipment/contribution.py:79-103`
- Test: `tests/unit/equipment/test_normalizer.py`, `tests/unit/equipment/test_contribution.py`

**Interfaces:**
- Produces: `strip_mod_tags(text: str) -> str` in `companion/equipment/normalizer.py` — removes ` (implicit)`, `(augmented)`, `(fractured)`, `(enchant)`, `(rune)`, `(crafted)`, `(desecrated)` (case-insensitive) and strips; `normalize_modifier` uses it in place of its inline `re.sub`.
- Produces: `NormalizedModifierType.ALL_ELEMENTAL_RESISTANCE = "ALL_ELEMENTAL_RESISTANCE"`, `NormalizedModifierType.ALL_ATTRIBUTES = "ALL_ATTRIBUTES"` (placed after CHAOS_RESISTANCE and INTELLIGENCE respectively).

- [ ] **Step 1: Write the failing tests** in `tests/unit/equipment/test_normalizer.py`

```python
@pytest.mark.parametrize("line,mtype,value", [
    ("+12% to all Elemental Resistances", NormalizedModifierType.ALL_ELEMENTAL_RESISTANCE, 12.0),
    ("+12(10-15)% to all Elemental Resistances", NormalizedModifierType.ALL_ELEMENTAL_RESISTANCE, 12.0),
    ("+8 to all Attributes", NormalizedModifierType.ALL_ATTRIBUTES, 8.0),
    ("Gain 10% of Damage as Extra Fire Damage", NormalizedModifierType.EXTRA_FIRE_DAMAGE, 10.0),
    ("+1 to Level of all Fire Spell Skills", NormalizedModifierType.FIRE_SPELL_LEVEL, 1.0),
    ("+2 to Level of all Spell Skills", NormalizedModifierType.ALL_SPELL_LEVEL, 2.0),
    ("+20% to Fire Resistance (rune)", NormalizedModifierType.FIRE_RESISTANCE, 20.0),
])
def test_poe2_wordings(line, mtype, value):
    mod = normalize_modifier(line)
    assert (mod.modifier_type, mod.value) == (mtype, value)
    assert mod.raw_text == line

def test_all_res_is_global_unless_conditional():
    assert normalize_modifier("+10% to all Elemental Resistances").scope == ModifierScope.GLOBAL_CHARACTER_STAT
    assert normalize_modifier("+10% to all Elemental Resistances while on Full Energy Shield").scope == ModifierScope.CONDITIONAL

def test_flat_maximum_energy_shield_local_only_on_defence_slots():
    assert normalize_modifier("+30 to maximum Energy Shield", slot=SlotType.HELMET).modifier_type == NormalizedModifierType.LOCAL_ENERGY_SHIELD
    assert normalize_modifier("+30 to maximum Energy Shield", slot=SlotType.RING).modifier_type != NormalizedModifierType.LOCAL_ENERGY_SHIELD

def test_strip_mod_tags():
    assert strip_mod_tags("Adds 1 to 4 Physical Damage to Attacks (implicit)") == "Adds 1 to 4 Physical Damage to Attacks"
    assert strip_mod_tags("+20 to Spirit (Rune)") == "+20 to Spirit"
```

And in `tests/unit/equipment/test_contribution.py`: an item with `ALL_ELEMENTAL_RESISTANCE` value 10 (GLOBAL) gives `fire_res_delta == cold_res_delta == lightning_res_delta == 10` and `chaos_res_delta == 0`; an item with `ALL_ATTRIBUTES` value 8 gives `str_delta == dex_delta == int_delta == 8`; a CONDITIONAL all-res mod adds nothing.

- [ ] **Step 2: Run** `uv run pytest tests/unit/equipment/test_normalizer.py tests/unit/equipment/test_contribution.py -q` — Expected: new tests FAIL.

- [ ] **Step 3: Implement**
  - schema: the two enum values.
  - normalizer: `strip_mod_tags`; wire `RE_ALL_RES` (after chaos res) and `RE_ALL_ATTR` (after intelligence), same shape as the single-res/attribute branches; widen `RE_EXTRA_FIRE` to `Gain (\d+)% of (?:Physical\s+)?Damage as Extra Fire Damage`; `RE_FIRE_SPELL_LEVEL` / `RE_ALL_SPELL_LEVEL` end in `Skill(?:\s+Gem)?s`; `RE_LOCAL_ES_FLAT` to `to\s+(?:maximum\s+)?Energy\s+Shield`.
  - contribution: inside the GLOBAL_CHARACTER_STAT branch, ALL_ELEMENTAL_RESISTANCE adds to fire/cold/light; ALL_ATTRIBUTES adds `int(value)` to str/dex/int.

- [ ] **Step 4: Run** the two test files, then `uv run pytest -q -x --ignore=tests/e2e` — Expected: all pass (existing old-wording tests included).

- [ ] **Step 5: Commit** `feat(normalizer): wire all-res/all-attributes, PoE2 wordings, strip_mod_tags`

### Task 2: Tag-free text family in guide priorities

**Files:**
- Modify: `companion/builds/priorities.py:15-19`
- Test: `tests/unit/builds/test_priorities.py`

**Interfaces:**
- Consumes: `strip_mod_tags(text: str) -> str` from Task 1.

- [ ] **Step 1: Write the failing tests**

```python
def test_mod_family_ignores_clipboard_tags():
    assert mod_family("Adds 1 to 4 Physical Damage to Attacks (implicit)") == mod_family("Adds 2 to 4 Physical Damage to Attacks")
    assert mod_family("+20 to Spirit (rune)") == mod_family("+30 to Spirit")

def test_mod_family_keeps_ranges_numeric():
    assert mod_family("Gain 12(10-15) Rage on Hit (implicit)") == mod_family("Gain 3 Rage on Hit")

def test_priority_signal_matches_implicit_candidate():
    item = StageItem(slot="Ring 1", name="Iron Ring", item_class="Ring",
                     mods=["Adds 2 to 4 Physical Damage to Attacks"])
    assert priority_signal(item, ["Adds 1 to 4 Physical Damage to Attacks (implicit)"]).matched == 1
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/builds/test_priorities.py -q` — Expected: new tests FAIL.

- [ ] **Step 3: Implement** — the text-fallback branch of `mod_family` applies `strip_mod_tags(line)` before number substitution.

- [ ] **Step 4: Run** `uv run pytest -q -x --ignore=tests/e2e` — Expected: all pass.

- [ ] **Step 5: Commit** `fix(priorities): ignore clipboard tags in mod family`

### Final check (orchestrator)

Re-run the scan script from the analysis and record before/after unknown counts in the ledger; full `uv run pytest -q` including e2e.

Skipped on purpose: types for mana, spirit, minion levels, rarity and the other 80 families (no consumer; add when a dimension needs them); dual resistances such as `to Cold and Chaos Resistances` (1 guide line; add when it shows up in a real compare).
