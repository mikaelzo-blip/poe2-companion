# Hermes PoE2 Companion — Blueprint v2
## Fubgun 0.5.5 Flameblast / Oil Grenade
### Read-Only Observation, Deterministic Build Brain, Persistent Journey State, and Hermes Advisory Layer

**Status:** Authoritative Blueprint v2  
**Date:** 21 September 2026  
**Supersedes:** `POE2_Hermes_Companion_Blueprint_v1.md`  
**Target build:** Fubgun `0.5.5 Flameblast / Oil Grenade`  
**Class:** Mercenary  
**Ascendancy:** Gemling Legionnaire  

---

# 0. Why v2 Exists

Blueprint v1 had the correct product direction, but several architectural assumptions were too optimistic or too loosely enforced.

The most important changes in v2 are:

1. **Hermes is no longer the continuous sensor.**
   - Continuous observation is moved into a separate **read-only sensor daemon**.
   - Hermes remains the reasoning/advisory layer.
   - Hermes `computer_use` is not used as the unattended continuous watcher.

2. **No-input is enforced by architecture, not by a YAML promise.**
   - The unattended daemon contains no game-input module.
   - No `pyautogui`, `pynput`, keyboard/mouse drivers, `SendInput`, `PostMessage` game-control path, or cua-driver connection exists in the sensor daemon.
   - Hermes companion profile uses manual approvals and must never run in `--yolo`.

3. **Without official API access, character-state automation is partial, not total.**
   - `Client.txt` cannot supply complete passive/gear/skill state.
   - Vision should not attempt to read an entire passive tree continuously.
   - Mode B therefore includes **guided checkpoints** and **Gear Audit**.

4. **Level 52 transition is persistent state, not a one-level stage.**
   - If the companion is installed at level 60, it still checks whether the transition was actually completed.
   - `level >= 52` plus incomplete transition creates a transition flag.

5. **`.build` parsing follows the real schema.**
   - `level_interval` is modeled as `FUTURE | ACTIVE | EXPIRED | UNKNOWN`.
   - Passive comparison preserves weapon-set context.
   - Passive dedup is not performed on `id` alone.

6. **Target truth and player-state truth are separated.**
   - Fubgun written rules, `.build`, adjacent stages, and PoB2 define target/reference truth.
   - API/log/vision/manual checkpoints define actual player state.

7. **One canonical roadmap replaces multiple conflicting roadmaps.**
   - M0 → M10 is the only authoritative implementation order.

---

# 1. Product Definition

The system is an **AI journey director for Path of Exile 2**.

Its job is to:

```text
OBSERVE
  ↓
NORMALIZE
  ↓
RECONCILE
  ↓
COMPARE
  ↓
DECIDE
  ↓
NOTIFY / EXPLAIN
```

It is **not** a game-playing bot.

The product target is:

> Hermes knows where the character is, what build stage/variant is relevant, what is missing, what is dangerous, what should be done next, and why — while the player still performs every in-game action.

---

# 2. Automation Contract

## 2.1 Automatic

The companion may automatically:

- detect whether PoE2 is running
- detect session start/stop
- read `Client.txt` in read-only mode
- parse recognized log events
- take read-only OS screenshots of the PoE2 window
- crop relevant regions
- send cropped screenshots to a configured vision model
- parse character-panel values
- parse a stable visible tooltip
- call the official GGG API when valid OAuth credentials exist
- obey API rate limits and circuit breakers
- update local state
- determine the active progression phase
- determine the build target variant
- compare current state with Fubgun references
- detect transition blockers
- detect mechanic conflicts when observable
- prioritize the next objective
- generate templated alerts
- produce recaps
- answer "why?" and "what next?" through Hermes
- research updated public build information when explicitly requested

## 2.2 Player-only

The companion must not automatically:

- move the character
- click inside PoE2
- type into PoE2
- press skills
- flask
- dodge
- loot
- equip items
- move inventory items
- allocate passives
- spend gold
- use currency
- craft
- vendor
- accept quests
- interact with NPCs
- trade
- trigger any game-affecting action from:
  - a timer
  - a file change
  - a `Client.txt` event
  - a screenshot
  - an LLM decision
  - an API response

The system must not expose a future "autoplay" toggle.

---

# 3. Compliance Architecture

## 3.1 Hard no-input boundary

The unattended daemon must contain **no game-input capability**.

Forbidden imports / mechanisms inside the daemon include:

```text
pyautogui
pynput
keyboard
mouse
game automation libraries
ctypes SendInput
keybd_event
mouse_event
cua-driver input path
DirectInput injection
DLL injection
game-memory write
game-memory read
game hook
DirectX hook
overlay injection
```

The daemon may detect the game process **by name/existence only**.

It must not open the game process with memory-reading rights.

## 3.2 Hermes companion profile

Use a dedicated Hermes profile for this project.

Requirements:

```text
approvals.mode = manual
never run with --yolo
never run with /yolo
never set approvals.mode = off
```

`SKILL.md` must explicitly state:

```text
When Path of Exile 2 is the target application:
- capture/read is permitted
- click/type/drag/scroll/key/focus actions that affect the game are prohibited
```

## 3.3 Static no-input test

CI/pre-commit must fail if unattended companion code imports or references prohibited input mechanisms.

Example rule:

```text
FAIL BUILD if companion daemon contains:
- pyautogui
- pynput
- keyboard
- mouse
- SendInput
- keybd_event
- mouse_event
- cua-driver input client
```

## 3.4 Read-only file rule

Allowed:

```text
read Client.txt
read companion source files
read user BuildPlanner directory
read local companion state
```

Allowed with explicit opt-in:

```text
copy valid .build files into the official user BuildPlanner directory
```

Not allowed:

```text
modify game executable
modify packed game data
write internal game files
inject overlays into the game process
```

---

# 4. GGG API Compliance

When official API integration is available:

## 4.1 OAuth

Use a **public OAuth client**.

Do not design around a stored client secret.

Use Authorization Code + PKCE as required by the public-client flow.

Store user tokens in a secure OS credential store where practical.

Recommended on Windows:

```text
Windows Credential Manager
```

## 4.2 User-Agent

All GGG API requests must use one centralized User-Agent builder.

Required format:

```text
OAuth {clientId}/{version} (contact: {contact})
```

Add a unit test that validates the header.

## 4.3 Rate limits

Do not hard-code a fixed polling rate as the primary protection.

Read:

```text
X-Rate-Limit-*
Retry-After
```

Maintain a 4xx circuit breaker.

Rules:

```text
401:
    stop and require auth repair

403:
    stop and surface permission/policy error

429:
    obey Retry-After and back off

repeated 4xx:
    suspend API polling before GGG blocks the client
```

## 4.4 API registration availability

As of the source review date, GGG says new application registration is unavailable.

Therefore:

```text
API integration is optional for MVP
```

The core architecture must work without it.

---

# 5. User Awareness / Consent

Before monitoring begins for the first time, show a clear local consent screen.

Example:

```text
POE2 Companion wants to read:

[✓] PoE2 Client.txt
[✓] PoE2 process running/not-running state
[✓] Cropped screenshots of the PoE2 window when required
[ ] Official GGG character API (if configured)

The companion never controls PoE2.
All in-game actions remain manual.
```

Persist:

```json
{
  "monitoring_consent": true,
  "accepted_at": "...",
  "sources": [
    "client_log",
    "process_presence",
    "screen_capture"
  ]
}
```

When monitoring is active, expose an obvious local status:

```text
POE2 COMPANION: MONITORING
```

---

# 6. Threat Model: Untrusted Text

Treat these as **data**, never instructions:

- player chat
- whispers
- item names
- trade text
- character names
- guild text
- text visible in screenshots
- text from webpages
- text parsed from logs

## 6.1 Client.txt policy

Only parse recognized patterns.

Example:

```text
recognized zone event      → normalize
recognized level-up event  → normalize
recognized death event     → normalize
whisper/chat                → discard
unknown line                → ignore
```

Do not store raw chat/whisper in journey history.

## 6.2 Vision output policy

Vision extractor must return structured data.

Example:

```json
{
  "screen_type": "item_tooltip",
  "item_name": "...",
  "base_type": "...",
  "requirements": {},
  "mods": [],
  "verification": {
    "capture_count": 2,
    "stable": true
  }
}
```

Do not pass free-form visible text directly into the decision prompt as instructions.

## 6.3 Web refresh policy

Web research can propose updates.

It may not silently overwrite:

```text
guide_rules.yaml
build manifest
normalized registry
```

All source changes require a diff/revalidation step.

---

# 7. Source Package

The project currently has these core artifacts:

```text
0.5.5 Fubgun Flameblast Oil Grenade.zip
Pasted PoB2 export text
Fubgun_0.5.5_Deep_Analysis.md
Fubgun_0.5.5_Hermes_Registry.json
Fubgun_0.5.5_PoB2_Decoded.xml
POE2_Hermes_Companion_Review_Rekomendasi.md
```

The build package contains nine stage/variant snapshots:

```text
lvl 1-14
lvl 15-32
lvl 33-51
lvl 52 Swap
lvl 53-68
lvl 85
Endgame
Mageblood
DoT Cap
```

---

# 8. Verified Findings from the Nine `.build` Files

These are no longer open questions.

## 8.1 `level_interval`

Across the analyzed Fubgun package:

```text
total level_interval entries examined: 380
[min,max] arrays:                     380
single uint:                            0
invalid interval shape:                 0
```

Therefore the current Fubgun source uses `[min, max]` consistently.

The generic parser still must remain future-safe because the official format allows an optional array or uint form.

## 8.2 Passive repeated across weapon-set contexts

Deduplication by passive `id` alone is invalid.

Observed examples:

```text
Mageblood:
13 passive IDs appear in multiple weapon-set contexts

DoT Cap:
12 passive IDs appear in multiple weapon-set contexts
```

Therefore logical passive comparison must preserve weapon-set context.

Minimum logical key:

```python
(passive_id, weapon_set_context)
```

## 8.3 `weapon_set: 0`

In the current nine Fubgun files:

```text
explicit weapon_set = 1 → observed
explicit weapon_set = 2 → observed
explicit weapon_set = 0 → not observed
shared/default passives → field often omitted
```

Do not assume the semantics of explicit `0` until verified.

Normalization:

```text
field omitted → DEFAULT_OR_SHARED
1             → SPECIALISATION_1 candidate
2             → SPECIALISATION_2 candidate
0             → UNKNOWN_RESERVED until verified
```

## 8.4 Mageblood and DoT Cap are not simple supersets

Passive logical-pair deltas show substantial respec behavior.

Observed:

```text
lvl85 → Endgame
+14 / -2

Endgame → Mageblood
+33 / -27

Mageblood → DoT Cap
+68 / -65
```

Therefore "higher stage" cannot be modeled as "previous stage + more nodes".

## 8.5 Meta gem anomaly

`Cast on Dodge` appears in multiple Fubgun snapshots as a build skill with:

```text
level_interval = [58,100]
```

However the official Build Planner documentation states that meta gems are not currently supported by the planner.

Therefore retain it in the registry but annotate it.

Example:

```json
{
  "name": "Cast on Dodge",
  "eligible_from": 58,
  "source_present": true,
  "official_planner_support": false,
  "validation_mode": "guide_or_live_state"
}
```

## 8.6 `additional_text` markup

The analyzed Fubgun package contains non-empty `additional_text`, but current entries do not require the markup syntax mentioned by the generic Build Planner format.

A markup parser is still recommended for robustness, but it is not a current source blocker.

---

# 9. Source Authority — Split into Two Independent Hierarchies

Blueprint v1 mixed target knowledge and player-state evidence.

v2 separates them.

## 9.1 Target/reference hierarchy

Used to answer:

> What should the build look like?

Priority:

```text
1. Explicit written Fubgun mechanic/progression rule
2. Active Fubgun `.build` snapshot
3. Adjacent `.build` snapshots
4. PoB2 high-end reference
5. Hermes inference
```

Inference must always be labeled.

## 9.2 Actual player-state hierarchy

Used to answer:

> What does the player actually have now?

Priority is **per field**, not global.

Examples:

```text
level:
    Client.txt exact level-up event / API
    → vision
    → manual checkpoint

area:
    Client.txt
    → vision
    → manual

equipment:
    API
    → Gear Audit
    → targeted vision

skills:
    API
    → guided skill audit
    → targeted vision

passives:
    API
    → deterministic exported/checkpoint source
    → targeted manual verification

resistances / life / armour / evasion:
    character-panel vision
    → trusted local calculation if available

gold:
    vision/manual
```

---

# 10. Canonical Architecture

```text
                          FUBGUN SOURCE PACKAGE
                   .build + written rules + PoB2
                                  │
                                  ▼
                            BUILD REGISTRY
                                  │
                                  ▼
                            BUILD BRAIN
                                  │
                                  │
 ┌────────────────────────────────┼─────────────────────────────────┐
 │                                │                                 │
 │                         PLAYER-STATE LAYER                       │
 │                                                                  │
 │     ┌────────────────┐   ┌────────────────┐   ┌──────────────┐  │
 │     │ Client.txt     │   │ OS Screenshot  │   │ GGG API      │  │
 │     │ read-only      │   │ read-only      │   │ optional     │  │
 │     └───────┬────────┘   └────────┬───────┘   └──────┬───────┘  │
 │             │                     │                  │          │
 │             └──────────────┬──────┴──────────────┬───┘          │
 │                            ▼                     │              │
 │                     SENSOR DAEMON               │              │
 │                no input capability              │              │
 │                            │                     │              │
 │                            ▼                     │              │
 │                     OBSERVATION BUS ◄────────────┘              │
 │                            │                                    │
 │                            ▼                                    │
 │                     STATE RECONCILER                            │
 │                            │                                    │
 │                            ▼                                    │
 │                    CHARACTER_STATE v2                           │
 └────────────────────────────┼─────────────────────────────────────┘
                              │
                              ▼
                         BUILD DELTA
                              │
                              ▼
                       RULE EVALUATION
                              │
                              ▼
                     OBJECTIVE ENGINE
                              │
                  ┌───────────┴───────────┐
                  ▼                       ▼
          TEMPLATE ALERTS             HERMES
            deterministic        explain / research /
                                 answer / manual capture
                  │                       │
                  └───────────┬───────────┘
                              ▼
                            PLAYER
                              │
                              ▼
                       MANUAL GAME INPUT
```

---

# 11. Sensor Daemon vs Hermes

This boundary is critical.

## 11.1 Sensor daemon

Runs continuously while PoE2 is active.

May:

```text
read log
check process existence
capture OS window
crop regions
invoke configured vision service
call official API
update observations
```

May not:

```text
click
type
focus game
send keys
move mouse
control game
```

## 11.2 Hermes

Hermes reads:

```text
CURRENT_OBJECTIVE.json
CHARACTER_STATE
build rules
relevant registry subset
journey history
```

Hermes is used for:

- explanation
- natural-language advisory
- deeper troubleshooting
- public-web research
- manual-present commands such as `cek layar`
- translating structured alerts into useful advice

Hermes is not the continuous polling loop.

---

# 12. OS Screenshot Strategy

The sensor daemon should use a **capture-only OS API/library**.

The exact implementation must be selected during M7, but the capability contract is fixed:

```text
capture-only
no mouse/keyboard control
targeted PoE2 window
crop before model submission where possible
```

Recommended PoE2 display setup:

```text
Windowed or Borderless
English client language initially
known UI scale
known resolution
```

Fullscreen-exclusive support must be smoke-tested rather than assumed.

---

# 13. Vision Budget

Vision is not free.

Use an explicit budget.

Example config:

```yaml
vision:
  enabled: true
  max_calls_per_hour: 120
  minimum_seconds_between_general_captures: 15
  stable_tooltip_captures_required: 2
  screenshot_cache_ttl_minutes: 30
  screenshot_cache_max_mb: 500
```

General gameplay screenshot should be rare.

Prefer:

```text
event-driven capture
targeted crop
stable tooltip detection
dedupe by perceptual hash
```

---

# 14. Vision Privacy

Config must declare:

```yaml
vision_provider:
  mode: cloud | local
  provider: ...
```

If cloud:

> Cropped PoE2 image regions are transmitted to the configured model provider for visual analysis.

If local:

> Image processing remains local according to the local model setup.

Do not claim that "screenshots stay local" merely because Hermes does not show them as attachments.

---

# 15. Screen Types

The vision classifier should first identify the screen type.

Supported in v0.3/v0.4:

```text
CHARACTER_PANEL
ITEM_TOOLTIP
SKILL_PANEL
PASSIVE_SCREEN_TARGETED
UNKNOWN
```

## Character panel

Extract:

```text
life
mana
spirit
armour
evasion
fire resistance
cold resistance
lightning resistance
chaos resistance
```

## Item tooltip

Extract:

```text
rarity
item name
base type
requirements
implicit mods
explicit mods
runes/sockets when visible
level requirement
```

## Skill panel

Use only for targeted verification, not full continuous inventory.

## Passive screen

Use targeted verification only.

Do not attempt to continuously reconstruct hundreds of passive nodes from screenshots.

---

# 16. Verification States

Avoid pretending the LLM's self-reported confidence is calibrated.

Prefer semantic verification states:

```text
VERIFIED
CORROBORATED
SINGLE_SOURCE
STALE
UNKNOWN
CONFLICTING
```

Optional numeric score may be derived internally from procedure.

Examples:

```text
two matching captures + range valid:
    VERIFIED

one clean capture:
    SINGLE_SOURCE

API and audit disagree:
    CONFLICTING

old gear audit after detected equipment change:
    STALE
```

Critical alerts require sufficient verification.

---

# 17. Observation Schema

Every incoming fact becomes an observation.

```json
{
  "observation_id": "obs-...",
  "character_id": "...",
  "type": "VISIBLE_STAT",
  "key": "cold_res",
  "value": 61,
  "source": "vision_character_panel",
  "observed_at": "2026-09-21T03:00:00+07:00",
  "verification": "VERIFIED",
  "evidence": {
    "captures_matched": 2,
    "region": "character_panel"
  }
}
```

Log example:

```json
{
  "type": "LEVEL_UP",
  "value": 52,
  "source": "client_log",
  "verification": "VERIFIED"
}
```

---

# 18. Character State v2

State is stored **per character**.

Suggested layout:

```text
runtime/
  active_character.json
  characters/
    <character-id>.json
  current_objective.json
  session_state.json
  journey_history.jsonl
  alerts.jsonl
```

## Field wrapper

Each important fact uses:

```json
{
  "value": null,
  "source": null,
  "observed_at": null,
  "verification": "UNKNOWN",
  "stale_after": null,
  "evidence_ref": []
}
```

## Example

```json
{
  "schema_version": "2.0",

  "character": {
    "id": "...",
    "name": {
      "value": "...",
      "source": "client_log",
      "verification": "VERIFIED"
    },
    "class": {
      "value": "Mercenary",
      "source": "api",
      "verification": "VERIFIED"
    },
    "ascendancy": {
      "value": "Gemling Legionnaire",
      "source": "api",
      "verification": "VERIFIED"
    },
    "level": {
      "value": 52,
      "source": "client_log",
      "verification": "VERIFIED",
      "stale_after": "on:LEVEL_UP"
    }
  },

  "game_version": {
    "value": "0.5.5",
    "source": "registry_manifest",
    "verification": "VERIFIED"
  },

  "journey": {
    "area": {},
    "progression_phase": {},
    "target_variant": {},
    "flags": []
  },

  "transition": {
    "level_52": {
      "status": "VERIFYING",
      "verified_at": null,
      "requirements": {}
    }
  },

  "equipment": {
    "set1": {},
    "set2": {},
    "set3": {},
    "helmet": {},
    "body_armour": {},
    "gloves": {},
    "boots": {},
    "amulet": {},
    "ring1": {},
    "ring2": {},
    "belt": {},
    "charms": []
  },

  "skills": {
    "entries": [],
    "source_state": "UNKNOWN"
  },

  "passives": {
    "allocated": [],
    "specialisations": {
      "set1": [],
      "set2": [],
      "set3": []
    },
    "quest_stats": []
  },

  "visible_stats": {
    "life": {},
    "mana": {},
    "spirit": {},
    "armour": {},
    "evasion": {},
    "fire_res": {},
    "cold_res": {},
    "lightning_res": {},
    "chaos_res": {}
  },

  "resources": {
    "gold": {},
    "gcp": {}
  },

  "audit": {
    "gear_last_completed": null,
    "skill_last_completed": null,
    "passive_checkpoint_last_completed": null
  }
}
```

---

# 19. State Staleness Rules

Staleness is per field.

Examples:

```text
level:
    stale only when a newer level event occurs

area:
    stale on next area change

equipment:
    stale on API equipment diff
    or suspected manual gear change
    or Gear Audit TTL

visible resistances:
    stale on equipment/passive change
    or TTL

gold:
    short TTL

passive checkpoint:
    stale after passive allocation evidence
    or stage transition
```

A stale value may inform low-priority advice.

A stale value must not trigger a critical alert by itself.

---

# 20. Single Writer Rule

Only one process writes canonical runtime state.

Recommended:

```text
companion daemon = canonical writer
Hermes = reader / command caller
```

Hermes must not directly edit:

```text
runtime/*.json
```

Instead it calls companion CLI/API commands.

Example:

```text
poe2-companion explain
poe2-companion request-gear-audit
poe2-companion mark-transition-verified
```

Use atomic writes:

```text
write temp
fsync if needed
rename
```

Maintain rolling backups.

---

# 21. Build Planner `level_interval`

Generic parser:

```python
from enum import Enum

class Elig(Enum):
    ACTIVE = "active"
    FUTURE = "future"
    EXPIRED = "expired"
    UNKNOWN = "unknown"

def parse_level_interval(v):
    if v is None:
        return None

    if isinstance(v, list):
        if (
            len(v) == 2
            and all(isinstance(x, int) and x >= 0 for x in v)
            and v[0] <= v[1]
        ):
            return (v[0], v[1])
        raise SourceValidationError(v)

    if isinstance(v, int):
        return UnsupportedSingleUintInterval(v)

    raise SourceValidationError(v)
```

Eligibility:

```text
level unknown       → UNKNOWN
below min           → FUTURE
inside inclusive    → ACTIVE
above max           → EXPIRED
```

Apply to:

```text
passives
skills
supports
inventory slots
```

---

# 22. Passive Logical Identity

Do not use:

```python
unique(passive_id)
```

Use at minimum:

```python
(passive_id, weapon_set_context)
```

Intervals remain source metadata.

Example normalized structure:

```json
{
  "id": "some_passive_id",
  "weapon_set_context": "SPECIALISATION_1",
  "intervals": [
    [52, 100]
  ],
  "source_count": 2
}
```

Preserve the original raw list for audit.

---

# 23. Passive ID / Hash Mapping

The project eventually needs:

```text
Build Planner passive string ID
        ↔
official/API hash
        ↔
display name
```

Store mapping with version metadata.

Example:

```json
{
  "game_version": "0.5.5",
  "entries": {
    "strength89": {
      "api_hash": 12345,
      "display_name": "...",
      "status": "VERIFIED"
    }
  }
}
```

Unmapped nodes must become:

```text
UNMAPPED
```

not:

```text
MISSING
```

---

# 24. Progression Model v2

A single scalar `stage` is insufficient.

Use separate concepts.

## 24.1 Progression phase

```text
LEVELING_1_14
LEVELING_15_32
LEVELING_33_51
POST_52_53_68
LEVELING_69_84_FALLBACK
HIGH_END
```

## 24.2 Target variant

```text
NONE
LVL85
ENDGAME
MAGEBLOOD
DOT_CAP
```

## 24.3 Flags

Examples:

```text
TRANSITION_PREPARING
TRANSITION_PENDING
MISSED_TRANSITION
MANUAL_OVERRIDE
SOURCE_VERSION_MISMATCH
DATA_STALE
```

Resolver output:

```json
{
  "progression_phase": "POST_52_53_68",
  "target_variant": "NONE",
  "flags": [
    "TRANSITION_PENDING"
  ],
  "reason": [
    "level >= 52",
    "level52 transition not verified complete"
  ]
}
```

---

# 25. Level 52 Transition v2

Transition states:

```text
NOT_RELEVANT
PREPARING
VERIFYING
BLOCKED
READY
TRANSITIONING
COMPLETE
```

Rules:

```text
level < 52:
    PREPARING if transition resources matter
    otherwise NOT_RELEVANT

level >= 52 and status unknown:
    VERIFYING

level >= 52 and known requirement false:
    BLOCKED

all required known true:
    READY

player indicates performing swap:
    TRANSITIONING

post-swap validation succeeds:
    COMPLETE
```

## Missed transition

If:

```text
level > 52
and transition != COMPLETE
```

set:

```text
TRANSITION_PENDING
```

If validation shows old build remains:

```text
MISSED_TRANSITION
```

This alert outranks normal passive/gear optimization.

---

# 26. Requirement State

Every transition requirement is:

```text
true
false
null
```

Meaning:

```text
true  = verified ready
false = verified not ready
null  = unknown / requires verification
```

Example:

```json
{
  "staff": {
    "ready": null,
    "source": null,
    "verify_hint": "run Gear Audit for weapon set 1"
  }
}
```

Unknown is not ready.

Unknown is also not automatically a blocker.

It creates a `VERIFY` task.

---

# 27. Fubgun Mechanic Rules

Store rules in `guide_rules.yaml`.

Every rule must include observability.

Example:

```yaml
rules:
  - id: weapon_types_after_transition
    severity: critical
    source:
      type: written_guide
      version: 0.5.5
    condition:
      min_level: 52
    expected:
      set1_weapon_type: staff
      set2_weapon_type: crossbow
    observable_via:
      - api
      - gear_audit
      - vision
    evaluable: true

  - id: frost_bomb_progression
    severity: high
    source:
      type: written_guide
      version: 0.5.5
    behavior:
      maintain_when_snapshot_omits: true
    observable_via:
      - skill_audit
      - api
      - vision
    evaluable: true

  - id: cast_on_dodge_future_requirement
    severity: medium
    source:
      type: fubgun_build
    eligibility:
      min_level: 58
    observable_via:
      - api
      - skill_audit
      - vision
    planner_support:
      official_meta_gem_support: false
```

A rule without an observation path must be:

```text
evaluable: false
```

---

# 28. Rule Evaluation States

A rule result is not boolean-only.

Use:

```text
PASS
FAIL
UNKNOWN
NOT_APPLICABLE
STALE
CONFLICTING_EVIDENCE
```

Critical alert requires:

```text
FAIL
+
verified evidence
```

---

# 29. Mode A and Mode B

## Mode A — Official API available

Preferred structured sources:

```text
equipment
skills
passives
specialisations
quest_stats
character metadata
```

Vision remains useful for:

```text
visible derived stats
unequipped item tooltip
UI troubleshooting
gold
```

## Mode B — No API

This is the expected MVP environment.

Automatic:

```text
session detection
area
level-up events
death events if log fixture supports them
visible stats
visible tooltip
```

Guided checkpoints:

```text
Gear Audit
Skill Audit
Passive Checkpoint
Transition Verification
```

The system must clearly show when state is incomplete.

Example:

```text
PASSIVE DELTA
Status: UNVERIFIED

Reason:
No API and no recent passive checkpoint.

Action:
Run passive checkpoint before using passive-delta alerts.
```

---

# 30. Gear Audit

Command:

```text
audit gear
```

Workflow:

```text
1. User opens inventory.
2. Companion requests one slot at a time.
3. User hovers the requested equipped item.
4. Sensor waits for stable tooltip.
5. Two matching captures are parsed.
6. Item is normalized.
7. Store item hash + parsed mods + evidence.
8. Move to next slot.
```

No automatic mouse movement.

Slots:

```text
weapon set 1
weapon set 2
helmet
body armour
gloves
boots
amulet
ring 1
ring 2
belt
charms
```

Stored result:

```json
{
  "slot": "boots",
  "item_hash": "...",
  "observed_at": "...",
  "verification": "VERIFIED",
  "mods": []
}
```

---

# 31. Skill Audit

Use when API is unavailable.

Goal:

```text
core skills
supports
key utility skills
transition-critical skills
```

Do not require a full exhaustive audit every session.

Trigger:

```text
stage boundary
transition verification
skill configuration warning
manual request
```

---

# 32. Passive Checkpoint

Do not OCR the entire passive tree continuously.

Preferred order:

```text
1. official API
2. deterministic exported tree data / documented format if available
3. guided checkpoint
4. targeted vision verification
```

Store:

```text
verified passive checkpoint timestamp
game version
source type
hash of normalized passive state
```

---

# 33. Client.txt Watcher

Must be read-only.

Required behaviors:

```text
tail appended lines
detect truncation / rotation
handle partial final line
handle long session gap
do not lock the file
do not persist raw chat
```

Known event fixtures must come from the user's own log during development.

Do not assume community parser strings are stable forever.

Initial event types:

```text
SESSION_ACTIVITY
AREA_CHANGED
LEVEL_UP
DEATH      # only after fixture confirms
CHARACTER_IDENTITY_HINT
```

---

# 34. Character Identity

A session may switch characters.

State must not be global-only.

Use:

```text
active_character
character store per character
```

Character identity can come from:

```text
API
confirmed log patterns
manual selection
```

If uncertain:

```text
CHARACTER_UNKNOWN
```

Do not merge two characters' journeys.

---

# 35. Build Delta Engine

Inputs:

```text
actual character state
target reference
eligibility status
target/reference rules
state freshness
```

Outputs:

```json
{
  "passives": {},
  "skills": {},
  "equipment": {},
  "transition": {},
  "mechanic_rules": {}
}
```

Do not convert UNKNOWN state into MISSING.

Example:

```text
MISSING:
verified player does not have target

UNKNOWN:
not enough evidence
```

---

# 36. Skill Classification

High-end Fubgun references contain many skills.

Normalize roles:

```text
CORE_ROTATION
UTILITY
DEBUFF
PERSISTENT
TRIGGERED
SNAPSHOT_UTILITY
FUTURE_TARGET
UNKNOWN_ROLE
```

The advisor must never imply that every registered skill is a button the player must actively press.

---

# 37. Equipment Evaluation

The evaluator answers:

```text
Is it usable now?
Is it an upgrade now?
Is it mechanically safe?
Is it worth investment?
How long will it remain useful?
How close is it to current target?
How close is it to next target?
```

Labels:

```text
CRITICAL_FIX
CLEAR_UPGRADE
SMALL_UPGRADE
SIDEGRADE
TEMPORARY
FUTURE_ITEM
NOT_RECOMMENDED
MECHANIC_CONFLICT
UNKNOWN_NEEDS_MORE_INFO
```

No opaque "87/100 item score" is required for user-facing output.

---

# 38. PoB2 Role

PoB2 is a **reference/simulation layer**.

It is not live truth.

It may supply:

```text
high-end item rolls
gem levels
gem quality
jewels
calculated Ignite DPS
calculated EHP
calculated armour
configuration assumptions
custom modifiers
```

Every simulated metric must retain assumptions.

Example:

```json
{
  "metric": "armour",
  "value": 80088,
  "source": "pob2_reference",
  "assumptions": [
    "custom modifier present"
  ]
}
```

Never say:

> Your character should literally show 80,088 armour

unless live state and assumptions are actually synchronized.

---

# 39. Objective Engine v2

Do not use fake precision such as:

```text
82.4 priority
```

Use deterministic categorical rank.

Order:

```text
1. CRITICAL_MECHANIC_BREAK
2. HARD_BLOCKER
3. SURVIVAL_RISK
4. TRANSITION_REQUIREMENT
5. CURRENT_PROGRESSION
6. STRONG_UPGRADE
7. OPTIMIZATION
8. FUTURE_PREPARATION
```

Tie-break:

```text
VERIFIED > SINGLE_SOURCE > STALE/UNKNOWN
CURRENT > FUTURE
HIGH_COST_OF_IGNORING > LOW
OLDER_UNRESOLVED_CRITICAL > NEW_MINOR
```

The result must be deterministic for a fixed state.

---

# 40. Alert Layer

Prefer deterministic templates.

Example:

```text
[CRITICAL]
Weapon configuration does not match the verified transition rule.

DO NOW
Verify weapon set 1 / set 2 setup.

SOURCE
Fubgun rule + Gear Audit
```

Use LLM only for:

```text
why?
explain more
what are my alternatives?
deep troubleshooting
```

This lowers latency, token use, and hallucination risk.

---

# 41. Safe-Zone Notification Policy

Non-critical alerts should be batched when possible.

Possible safe zones:

```text
town
hideout
other verified non-combat areas
```

Do not hard-code town names before fixtures/source list is created.

Policy:

```text
critical:
    notify immediately

non-critical:
    queue
    deliver in safe zone
    or include in session recap
```

---

# 42. Notification Channels

At least one must exist before v0.2 is considered useful.

Recommended order:

```text
1. Windows toast
2. Separate local companion window
3. Optional Hermes messaging gateway
```

Do not inject an overlay into PoE2.

---

# 43. Session Recap

At session end:

```text
SESSION RECAP

Started:
Level 31

Ended:
Level 36

Build stage:
lvl 33-51

Changed:
- 5 levels gained
- boots upgraded
- cold resistance improved
- 3 target passives confirmed

Still unresolved:
- Frost Bomb verification
- transition gold unknown

Next session:
Prepare lvl52 transition resources
```

Recap must be generated from journey history, not model memory.

---

# 44. Patch Drift

Manifest must include:

```text
target_game_version
guide_version
guide_updated_at
source_hashes
registry_version
mapping_version
```

On startup:

```text
if live/configured game version != registry target:
    SOURCE_VERSION_MISMATCH
```

Behavior:

```text
do not silently trust stale build rules
lower confidence for patch-sensitive rules
offer build source refresh/revalidation
```

---

# 45. Source Manifest

Example:

```json
{
  "manifest_version": "1.0",
  "target_game_version": "0.5.5",
  "build_name": "Fubgun Flameblast Oil Grenade",
  "author": "Fubgun",
  "guide_updated": "2026-09-12",

  "files": [
    {
      "path": "data/source/builds/lvl_1_14.build",
      "sha256": "..."
    },
    {
      "path": "data/source/pob2.xml",
      "sha256": "..."
    }
  ]
}
```

---

# 46. Official BuildPlanner Integration

Third-party tools may produce `.build` files for the documented BuildPlanner directory.

Optional feature:

```text
Install current recommended .build
```

Rules:

```text
explicit user opt-in
copy only valid .build
write only to documented user BuildPlanner directory
never modify game install directory
verify hash after copy
```

The value of the companion is not to duplicate the in-game BuildPlanner.

Its value is:

```text
cross-stage reasoning
journey state
transition logic
gear evaluation
warning prioritization
troubleshooting
```

---

# 47. Hermes Skill

Project-local path:

```text
.hermes/skills/poe2-fubgun-companion/
```

Suggested files:

```text
SKILL.md
RULES.md
WORKFLOW.md
TROUBLESHOOTING.md
```

Large registry data stays outside skill prompt files.

## SKILL.md core contract

```text
1. Read CURRENT_OBJECTIVE first.
2. Read only required CHARACTER_STATE fields.
3. Read current target/reference stage/variant.
4. Apply verified guide rules.
5. Never treat UNKNOWN as MISSING.
6. Never treat stale state as a verified blocker.
7. Use targeted capture only when the player is present and asks for visual inspection.
8. Never control PoE2.
9. Explain source/evidence when recommending a correction.
```

Project-local skills must be trusted during setup according to Hermes project-skill behavior.

---

# 48. Recommended Project Structure v2

```text
C:\Projects\poe2-companion\
│
├── README.md
├── pyproject.toml
├── .gitignore
├── config\
│   ├── companion.yaml
│   └── notification.yaml
│
├── companion\
│   ├── main.py
│   │
│   ├── compliance\
│   │   ├── no_input_guard.py
│   │   ├── consent.py
│   │   └── api_policy.py
│   │
│   ├── sources\
│   │   ├── manifest.py
│   │   ├── build_loader.py
│   │   ├── pob2_loader.py
│   │   ├── guide_rules.py
│   │   └── mappings.py
│   │
│   ├── sensing\
│   │   ├── process_presence.py
│   │   ├── client_log.py
│   │   ├── capture.py
│   │   ├── crop.py
│   │   ├── vision.py
│   │   └── api_provider.py
│   │
│   ├── observations\
│   │   ├── schema.py
│   │   └── bus.py
│   │
│   ├── state\
│   │   ├── schema.py
│   │   ├── store.py
│   │   ├── reconciliation.py
│   │   ├── staleness.py
│   │   └── backup.py
│   │
│   ├── build\
│   │   ├── interval.py
│   │   ├── progression.py
│   │   ├── passive_delta.py
│   │   ├── skill_delta.py
│   │   ├── gear.py
│   │   ├── transition.py
│   │   ├── rules.py
│   │   └── pob_reference.py
│   │
│   ├── objective\
│   │   ├── candidates.py
│   │   ├── ranking.py
│   │   ├── current.py
│   │   └── templates.py
│   │
│   ├── audit\
│   │   ├── gear_audit.py
│   │   ├── skill_audit.py
│   │   └── passive_checkpoint.py
│   │
│   ├── notify\
│   │   ├── windows_toast.py
│   │   ├── safe_zone.py
│   │   └── dedupe.py
│   │
│   └── cli.py
│
├── data\
│   ├── source\
│   │   ├── manifest.json
│   │   ├── builds\
│   │   ├── pob2.xml
│   │   └── guide_rules.yaml
│   │
│   ├── normalized\
│   │   └── fubgun_registry.json
│   │
│   ├── mappings\
│   │   ├── passive_id_hash.json
│   │   ├── gem_names.json
│   │   └── item_aliases.json
│   │
│   └── fixtures\
│       ├── client_log\
│       ├── screenshots\
│       └── states\
│
├── runtime\
│   ├── active_character.json
│   ├── current_objective.json
│   ├── session_state.json
│   ├── journey_history.jsonl
│   ├── alerts.jsonl
│   └── characters\
│
├── tests\
│   ├── compliance\
│   ├── source_validation\
│   ├── state\
│   ├── build\
│   ├── objective\
│   ├── log\
│   └── vision\
│
└── .hermes\
    └── skills\
        └── poe2-fubgun-companion\
            ├── SKILL.md
            ├── RULES.md
            ├── WORKFLOW.md
            └── TROUBLESHOOTING.md
```

---

# 49. Canonical Implementation Roadmap

This is the **only authoritative sequence**.

All old v1 Phase/MVP/Milestone ordering is superseded.

---

# M0 — Freeze and Validate Sources

## Goal

Make build data trustworthy before building logic.

## Deliverables

- validate nine `.build`
- validate JSON shapes
- normalize stage names
- preserve raw source
- create source manifest
- hash sources
- record guide/game version
- create initial `guide_rules.yaml`
- annotate meta-gem inconsistency
- validate current interval usage
- investigate/passively map weapon-set semantics
- create mapping placeholders

## Required findings

Record:

```text
single-uint interval occurrences
invalid intervals
duplicate passive logical pairs
weapon_set values observed
meta gem entries
markup usage
```

## Exit criteria

```text
source validator passes
manifest created
all known anomalies documented
```

---

# M1 — State Foundation

## Goal

Create reliable local state before any live sensors.

## Deliverables

- CHARACTER_STATE v2 schema
- per-character storage
- field provenance
- verification state
- staleness rules
- atomic write
- backup
- active-character pointer
- single-writer model

## Exit criteria

```text
state validates
crash-safe writes
two characters stay isolated
staleness transitions tested
```

---

# M2 — Offline Build Brain

## Goal

Given a synthetic state, determine the correct target and delta.

## Deliverables

- eligibility engine
- progression phase resolver
- target variant resolver
- passive logical-key handling
- passive delta
- skill delta
- UNKNOWN vs MISSING distinction
- source-conflict handling

## Tests

Property tests:

```text
min-1
min
max
max+1
unknown level
invalid interval
```

Golden scenarios for all progression phases.

## Exit criteria

```text
deterministic outputs
all stage fixtures pass
```

---

# M3 — Rules and Persistent Level-52 Transition

## Goal

Make transition behavior safe even when companion starts late.

## Deliverables

- rule schema
- `observable_via`
- rule evaluation states
- Level-52 transition persistence
- PREPARING / VERIFYING / BLOCKED / READY / COMPLETE
- MISSED_TRANSITION flag
- future requirement handling

## Required tests

```text
level 51 → PREPARING
level 52 unknown gear → VERIFYING
level 52 known missing requirement → BLOCKED
level 53 old build → MISSED_TRANSITION
install at level 60 + verified swapped → COMPLETE, no false warning
Cast on Dodge at 52 → FUTURE, not blocker
```

---

# M4 — Objective Engine and CLI

## Goal

Produce useful advice without any live game integration.

## Deliverables

- candidate schema
- categorical priority
- tie-break rules
- deterministic template output
- `CURRENT_OBJECTIVE.json`
- CLI evaluate command
- explanation source references

CLI:

```text
python -m companion evaluate runtime/characters/test.json
```

## v0.1 release

Exit criteria:

```text
offline state → correct current objective
static no-input test passes
```

---

# M5 — Session Monitor + Client.txt

## Goal

Add safe live session context.

## Deliverables

- process-presence monitor
- read-only Client.txt tailer
- log rotation handling
- partial line handling
- session gap handling
- observation bus
- state reconciler
- journey history

## Fixtures

Must be collected from the user's own PoE2 log.

Do not finalize parser regex before fixtures exist.

## v0.2 base

---

# M6 — Notification System

## Goal

Deliver actionable information without distracting the player.

## Deliverables

- Windows toast or selected local channel
- dedupe
- alert cooldown
- safe-zone queue
- session recap
- critical immediate path

## Exit criteria

```text
same warning not spammed
non-critical alert batched
critical verified alert immediate
```

---

# M7 — Read-Only Vision Sensor

## Goal

Observe visible derived stats safely.

## Deliverables

- capture-only OS window capture
- screen classifier
- crop
- character-panel parser
- verification procedure
- screenshot cache policy
- privacy/redaction
- cloud/local vision disclosure
- vision budget

## Fixtures

Real screenshots for:

```text
supported resolution(s)
supported UI scale(s)
English client
character panel
```

## v0.3 release

Critical alerts from vision are disabled until verification accuracy passes fixture threshold.

---

# M8 — Gear Auto-Analysis

## Goal

Evaluate candidate/equipped items without automatic mouse control.

## Deliverables

- stable-tooltip detection
- guided Gear Audit
- tooltip parser
- item hash
- gear TTL
- current-vs-target comparison
- investment advice
- mechanic-conflict detection when observable

Rename from v1:

```text
Gear Tooltip Autopilot
```

to:

```text
Gear Auto-Analysis
```

## v0.4 release

---

# M9 — Expanded Build Intelligence

## Goal

Add deeper advisory only after core state is reliable.

Add:

```text
Survival rules
Gear rules
Troubleshooting rules
minimal story guidance if supported
minimal economy guidance if supported
```

Do not create eight autonomous "directors" unless complexity later justifies it.

Functions/rules are preferred first.

---

# M10 — Official API + Deeper PoB2

## Goal

Complete structured character synchronization when official OAuth access is practical.

Add:

```text
official Character API
public OAuth + PKCE
User-Agent enforcement
4xx circuit breaker
passive hash mapping
equipment/skills structured provider
quest_stats
game metadata.version
deeper PoB2 comparison
```

## v1.0 release

---

# 50. Versioned Definition of Done

## v0.1 — Offline Brain

- [ ] all nine `.build` validated
- [ ] source manifest/hash created
- [ ] current Fubgun interval usage verified
- [ ] passive comparison preserves weapon-set context
- [ ] progression phase/variant resolution works
- [ ] Level-52 transition persists independently from exact level
- [ ] UNKNOWN never becomes MISSING automatically
- [ ] CLI produces `CURRENT_OBJECTIVE.json`
- [ ] static no-input test passes

## v0.2 — Live Log Session

- [ ] process presence works without memory access
- [ ] Client.txt is read-only
- [ ] fixtures from real local log exist
- [ ] level/area events parse
- [ ] character switching does not mix state
- [ ] state reconciler uses per-field provenance
- [ ] journey history persists
- [ ] consent is stored
- [ ] notification channel works

## v0.3 — Vision

- [ ] capture path has no input capability
- [ ] character panel parser works on fixtures
- [ ] two-capture verification works
- [ ] crop/redaction works
- [ ] cloud/local disclosure is explicit
- [ ] critical alerts require verified evidence
- [ ] vision budget works

## v0.4 — Gear

- [ ] guided Gear Audit works
- [ ] tooltip stability detection works
- [ ] item parser works
- [ ] item hash + TTL works
- [ ] current-stage evaluation works
- [ ] next-stage durability advice works
- [ ] mechanic conflicts are source-backed

## v1.0

- [ ] official API adapter available when credentials are possible
- [ ] public OAuth flow compliant
- [ ] User-Agent compliant
- [ ] 4xx circuit breaker tested
- [ ] passive mapping is versioned
- [ ] PoB2 metrics retain assumptions
- [ ] build patch drift detected
- [ ] alerts remain deduplicated
- [ ] session recap explains changes
- [ ] no automatic input to PoE2 exists

---

# 51. Testing Strategy

Testing moves forward in the roadmap, not Phase 10 only.

## Static compliance test

Fail if prohibited input paths appear.

## Property tests

For:

```text
level interval
state staleness
passive logical identity
```

## Golden scenarios

Examples:

```text
lvl 20 correct grenade build
lvl 33 Frost Bomb snapshot omission
lvl 51 pre-transition
lvl 52 unknown gear
lvl 52 ready
lvl 53 missed transition
lvl 60 installed after swap
lvl 85 high-end fallback
Mageblood respec
DoT Cap respec
```

## Screenshot fixtures

Include:

```text
character panel
item tooltip
comparison tooltip
different item rarity
different resolution
supported UI scale
```

## Log fixtures

Collected locally.

## API compliance tests

When API is added:

```text
User-Agent
PKCE/public client behavior
Retry-After
401 stop
403 stop
429 backoff
4xx breaker
```

---

# 52. Manual Override

Allow explicit player override.

Examples:

```text
set target variant mageblood
mark level52 transition complete
select active character
force gear audit stale
```

All overrides must be:

```text
timestamped
written to journey history
reversible
```

Hermes should distinguish:

```text
AUTO-DETECTED
vs
USER OVERRIDE
```

---

# 53. Failure Modes

## API unavailable

Continue with:

```text
log + vision + checkpoints
```

## Vision unavailable

Continue with:

```text
log + checkpoints + API if available
```

## Client.txt unavailable

Show:

```text
LOG SOURCE OFFLINE
```

Do not fabricate area/session data.

## Passive mapping unknown

Show:

```text
UNMAPPED
```

Do not report false missing nodes.

## Conflicting evidence

Set:

```text
CONFLICTING
```

and request targeted verification.

## Patch mismatch

Set:

```text
SOURCE_VERSION_MISMATCH
```

lower trust in patch-sensitive recommendations.

---

# 54. User-Facing Output Contract

Default advisory should be compact.

Example:

```text
CURRENT PHASE
lvl 33-51

DO NOW
Continue progression and protect level-52 transition resources.

VERIFY
Frost Bomb configuration is stale.

WATCH
Boots remain the weakest verified slot.

DO NOT DO
Do not treat Cast on Dodge as a level-52 blocker; its Fubgun interval begins at 58.

EVIDENCE
Client log + last Gear Audit + Fubgun 0.5.5 registry
```

If critical:

```text
CRITICAL BUILD ISSUE

Verified problem:
<problem>

Do now:
<single action>

Why:
<short explanation>

Evidence:
<sources>
```

---

# 55. Session Start Flow

```text
PoE2 process detected
        ↓
Load active character state
        ↓
Check source/game-version compatibility
        ↓
Open Client.txt read-only
        ↓
Start observation bus
        ↓
Resume unresolved objective
        ↓
If state stale:
    schedule verification
        ↓
Notify only if actionable
```

---

# 56. Session End Flow

```text
PoE2 process exits
        ↓
flush pending observations
        ↓
persist character state
        ↓
generate recap
        ↓
close session
        ↓
stop expensive sensing
```

---

# 57. Example: Install Companion at Level 60

Old v1 risk:

```text
Level 60 → assume lvl53-68
```

v2:

```text
Level 60
↓
Progression phase = POST_52_53_68
↓
Level52 transition state = UNKNOWN
↓
TRANSITION_PENDING
↓
Run verification
↓
if swapped:
    COMPLETE
else:
    MISSED_TRANSITION
```

No blind assumption.

---

# 58. Example: Candidate Boots

Observed stable tooltip:

```text
30% Movement Speed
+91 Life
+34 Cold Resistance
```

Current verified state:

```text
Cold Resistance = 61%
Current boots = 20% movement speed
```

Output:

```text
CLEAR UPGRADE

Why:
- improves movement speed
- adds life
- directly improves your verified cold-resistance weakness

Investment:
Use now.
Do not heavily overcraft if the next progression target replaces this slot soon.
```

No automatic equip.

---

# 59. Example: Unknown Passive State

Without API/checkpoint:

```text
PASSIVE DELTA
UNKNOWN

Reason:
No verified passive-state source is current.

Do now:
No critical passive warning.

If needed:
Run Passive Checkpoint.
```

This is preferable to hallucinating a missing node.

---

# 60. Example: Cast on Dodge at Level 52

Registry:

```text
Cast on Dodge
interval [58,100]
```

Output:

```text
FUTURE TARGET

Cast on Dodge is present in the Fubgun source package,
but its interval begins at level 58.

It is not a level-52 transition blocker.
```

Also retain:

```text
official planner meta-gem support = false
```

for source-aware validation.

---

# 61. Example: Patch Drift

Current registry:

```text
0.5.5
```

Detected/configured game:

```text
0.5.6
```

Output:

```text
BUILD SOURCE VERSION MISMATCH

Registry:
0.5.5

Game:
0.5.6

Action:
Continue with caution.
Patch-sensitive rules are downgraded until the build source is revalidated.
```

Do not silently rewrite the registry.

---

# 62. Deferred Features

Not required for v1:

- autonomous story route planner with full quest database
- advanced economy optimizer
- live full PoB simulation
- trade-site automation
- automatic `.build` switching without opt-in
- overlay injection
- speech/voice output
- multi-build generalization
- multi-game support

---

# 63. Decisions from Claude Review

## Adopted

- hard no-input boundary
- public OAuth client awareness
- User-Agent rule
- all-4xx breaker
- user-aware log monitoring
- prompt-injection treatment
- structured vision extraction
- level_interval state model
- passive `(id, weapon_set)` identity
- per-field provenance/staleness
- persistent Level-52 transition
- Mode B checkpoints
- daemon/Hermes separation
- single canonical roadmap
- earlier testing
- patch drift
- narrower v1 scope
- Auto-Analysis naming

## Modified

### Markup parser

Keep for robustness, but lower urgency because the current Fubgun package does not require it.

### Priority scoring

Do not adopt arbitrary numeric scoring.

Use categorical deterministic rank.

### Minimized-window behavior

Treat as a smoke-test requirement, not a product guarantee.

### Skill/project-local Hermes assumptions

Verified separately; keep project-local Hermes skill architecture.

### BuildPlanner copy

Allow third-party `.build` installation into the official user BuildPlanner directory with explicit opt-in and validation.

---

# 64. Decisions That Supersede Blueprint v1

The following v1 ideas are no longer authoritative:

```text
Hermes as continuous screenshot watcher
global API > screenshot > log precedence
dedup passive by id only
level == 52 as sole swap stage logic
single scalar stage for all high-end variants
eight Directors required for v1
vision confidence based mainly on model self-score
multiple competing implementation roadmaps
"immutable: true" config as sufficient no-input enforcement
```

---

# 65. Final Architecture Principle

The companion should be hard to misuse accidentally.

The system must make the safe path the easiest path:

```text
SENSOR DAEMON
can observe
cannot play

BUILD BRAIN
can compare
cannot play

OBJECTIVE ENGINE
can prioritize
cannot play

HERMES
can explain
can manually inspect with approvals
must not play

PLAYER
performs every in-game action
```

This is the design target for v2.

---

# 66. Immediate Next Step After v2

Do **not** start with vision.

Do **not** start with OAuth.

Do **not** start with notifications.

Start with:

```text
M0
Validate and freeze sources

M1
Build CHARACTER_STATE v2

M2
Build offline progression/delta brain

M3
Build persistent Level-52 transition

M4
Produce deterministic CURRENT_OBJECTIVE
```

Once v0.1 is trustworthy, connect live sensors.

The quality of this companion depends first on correct reasoning from known data, not on the number of live inputs.

---

# 67. Reference Sources

## Grinding Gear Games

Developer documentation:

`https://www.pathofexile.com/developer/docs`

API reference:

`https://www.pathofexile.com/developer/docs/reference`

Game / Build Planner file format:

`https://www.pathofexile.com/developer/docs/game`

Authorization:

`https://www.pathofexile.com/developer/docs/authorization`

## Hermes Agent

Computer Use:

`https://hermes-agent.nousresearch.com/docs/user-guide/features/computer-use`

Skills:

`https://hermes-agent.nousresearch.com/docs/user-guide/features/skills`

## Project Sources

- nine Fubgun `.build` snapshots
- supplied PoB2 export
- decoded PoB2 XML
- Fubgun normalized registry
- Blueprint v1
- Claude review/recommendation document

---

# 68. v2 Status

This document is now the authoritative conceptual and implementation blueprint for the project.

Implementation should reference:

```text
POE2_Hermes_Companion_Blueprint_v2.md
```

and treat Blueprint v1 as historical design context only.
