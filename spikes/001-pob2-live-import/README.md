# Spike 001: PoB2-Backed Live Character Import & Item Simulation PoC

## Summary
- **Backend:** `FabricioCasali/path-of-building-2-mcp` (cloned externally as sibling at `C:\Projects\path-of-building-2-mcp`).
- **Engine:** Headless Path of Building 2 running in Docker (`ghcr.io/pathofbuildingcommunity/pathofbuilding-tests:latest` + LuaJIT `mcp_entry.lua`).
- **Scope:** Zero production modification in `poe2-companion`. Validates live OAuth import, equipped helmet extraction, candidate item simulation, latency, and viability for live Ctrl+C loop.

---

## Given / When / Then Feasibility Matrix

| # | Spike Question | Given / When / Then | Risk | Outcome |
|---|---|---|---|---|
| 001 | Local Prerequisites | Given Docker Desktop, Python 3.11+, and Git, when checking environment, then all components are operational | Low | **VALIDATED** (Docker 29.7.2, Python 3.14/3.11, Git 2.53) |
| 002 | Headless Engine Boot | Given PoB2 Docker image and fork, when `mcp_entry.lua` boots, then JSON protocol passes ping and basic stat calculations | Medium | **VALIDATED** (Boot ~6.6s, JSON protocol stable) |
| 003 | GGG Live OAuth Flow | Given `client_id=pob` PKCE S256, when user authorizes in browser on `pathofexile.com`, then local listener captures code and exchanges bearer token | High | **VALIDATED** (Logged in, token cached at `%LOCALAPPDATA%\pob2-mcp\token.json`, 7 live characters retrieved) |
| 004 | Live Character Import | Given official GGG character payload, when imported into PoB2 engine, then tree, skills, and equipment load into memory | High | **VALIDATED with FIX** (GGG API sends structured mod objects `{"description": "..."}`; normalized before PoB2 ingestion) |
| 005 | Current Gear Extraction | Given imported live character, when querying `get_equipped(slot="Helmet")`, then exact raw item text is returned | Low | **VALIDATED** (Extracted `Brimstone Veil` on BOMSHAK / `Wrath Visor` on DaisyofWar) |
| 006 | Candidate Simulation | Given raw clipboard item, when calling `simulate_item(slot="Helmet", raw=...)`, then accurate Life, Resist, Defence, EHP, and DPS deltas are calculated | Medium | **VALIDATED** (Kraken Dome simulated accurately) |
| 007 | Live Ctrl+C Viability | Given a 1.4s simulation latency, when user presses Ctrl+C in game, then latency and game mechanic discrepancies dictate architectural role | High | **PARTIAL / CONSTRAINED** (Viable as asynchronous advisor, NOT as instantaneous synchronous replacement) |

---

## Detailed Results

### 1. Setup & Environment
- Docker: Docker Desktop 29.7.2 (Linux containers on Windows WSL2 backend).
- Python: `.venv` created under `C:\Projects\path-of-building-2-mcp\.venv` using Python 3.14 (Python 3.11.16 also verified).
- Fork: Pinned commit `ce8bffaba31f8e68cfce70579e1c96465e7c133c` with headless entrypoint `mcp_entry.lua`.

### 2. OAuth Result
- Flow: Authorization Code + PKCE (S256), `client_id=pob`, localhost listener port `49082`.
- Status: **SUCCESS** (`expires_in`: ~10 hours, cached on disk).
- Characters discovered:
  1. `BOMSHAK` — Level 17 Mercenary (League: Forbidden Rites)
  2. `DaisyofWar` — Level 71 Witch/Lich (League: Standard)
  3. `DespareBlood` — Level 68 Witch (League: Standard)
  4. `MadDrigo` — Level 32 Ranger (League: Standard)
  5. `MadDruiud` — Level 41 Druid (League: Standard)
  6. `Mikaelzo` — Level 33 Sorceress (League: Standard)
  7. `Mokeied` — Level 40 Monk (League: Runes of Aldur)

### 3. Live Character Import & Current Helmet
Tested on live character: **`BOMSHAK`** (Level 17 Mercenary, Forbidden Rites).
- Equipped gear loaded into PoB2:
  - Weapon 1: Dire Core (Tense Crossbow)
  - Helmet: **Brimstone Veil** (Hewn Mask)
  - Body Armour: Soul Skin (Quilted Vest)
  - Gloves: Gloom Grip (Riveted Mitts)
  - Boots: The Knight-errant (Mail Sabatons)
  - Rings/Amulet/Belt/Flasks/Charms: Blackheart, Ruby Ring, Ghoul Lash, Sapphire Charm, etc.
- Current Equipped Helmet (`get_equipped(slot="Helmet")`):
  ```
  Rarity: RARE
  Brimstone Veil
  Hewn Mask
  Evasion: 70
  Energy Shield: 32
  Item Level: 17
  +32 to Evasion Rating
  +11 to maximum Energy Shield
  34% increased Evasion and Energy Shield
  +36 to Accuracy Rating
  +12 to maximum Mana
  9% increased Rarity of Items found
  3.9 Life Regeneration per second
  10% increased Light Radius
  ```

### 4. Candidate Item Simulation
Pasted candidate helmet:
```
Item Class: Helmets
Rarity: Rare
Kraken Dome
Soldier Greathelm
--------
Armour: 45
--------
Requirements:
Level: 15
Str: 22
--------
Item Level: 19
--------
+20 to maximum Life
+7% to Lightning Resistance
1.2 Life Regenerated per second
```

#### Simulation Output Deltas:
- **Current Helmet:** `Brimstone Veil` (Hewn Mask)
- **Candidate Helmet:** `Kraken Dome` (Soldier Greathelm)
- **Life delta:** `+20` (361 -> 381)
- **Resistance deltas:**
  - Fire Resistance: `+0%` (-35% -> -35%)
  - Cold Resistance: `+0%` (-50% -> -50%)
  - Lightning Resistance: `+7%` (-43% -> -36%)
  - Chaos Resistance: `+0%` (0% -> 0%)
- **Defence deltas (Armour / Evasion / ES):**
  - Armour: `+10` (253 -> 263)
  - Evasion: `+0` (0 -> 0)
  - Energy Shield: `-32` (32 -> 0)
- **Total EHP delta:** `+6.74` (289.46 -> 296.20)
- **DPS delta:** `-1.82` (29.07 -> 27.25)

---

## Analysis of Mechanics & Fubgun Rules

### Why PoB2 Reported -1.82 DPS Delta on a Helmet
`Brimstone Veil` had `+36 to Accuracy Rating`, giving the low-level character 66% hit chance. Swapping to `Kraken Dome` dropped accuracy, decreasing hit chance and therefore PoB2's average hit DPS by 1.82.

### Why Grenade DPS Cannot Be Trusted as Authoritative
1. **Shotgunning & Trigger Dynamics:** Explosive Grenade and Gas Grenade rely on cluster overlap, fuse duration, fragmentation cycling, and ground ailment zones. PoB2's main output models a single grenade detonation per cooldown window rather than active volley density.
2. **Campaign Gear Prioritization:** Under Fubgun's campaign rules, armor slots (Helmet, Body, Gloves, Boots) are evaluated for defensive thresholds (Life, capped elemental resistances, base mitigation) and movement speed. They do NOT dictate weapon damage scaling. A -1.82 DPS drop from an accuracy affix on a helmet during Act 2 should NEVER cause a player to keep an uncapped, low-life helmet when a +20 Life, +7% Lightning Resistance helmet is available.
3. **Preservation:** The companion's rule engine (Fubgun campaign priorities, build breaker fire damage gates, resistance deficit scoring) must remain authoritative for gear recommendations. PoB2 provides rich calculation backing, not final gameplay verdicts.

---

## Latency Measurements

| Operation | Latency | Note |
|---|---|---|
| GGG API Character Fetch | **0.319s - 1.314s** | External network call to `api.pathofexile.com` |
| Headless PoB2 Cold Boot | **6.598s - 6.611s** | One-time Docker container start + passive tree init |
| PoB2 Character Import | **0.765s - 0.820s** | Parses tree nodes, skills, gems, and 12 gear slots |
| `simulate_item` (First Call) | **1.360s - 1.582s** | Clones build state, swaps item, recalculates, restores |
| `simulate_item` (Warm Call #1) | **1.381s - 1.561s** | Engine already hot in memory |
| `simulate_item` (Warm Call #2) | **1.405s - 1.821s** | Consistent ~1.4s - 1.6s execution time |

---

## Blockers & Discoveries

1. **PoE2 API Mod Format Change:**
   - **Issue:** Modern PoE2 GGG API returns explicit/implicit mods as objects `[{"description": "+32 to [Evasion] Rating"}]` instead of flat strings `["+32 to Evasion Rating"]`.
   - **Impact:** Upstream PoB2 `ImportTab.lua:1349` crashed with `attempt to call method 'gmatch' (a nil value)`.
   - **Resolution:** Added `_normalize_character_json` in `pob_mcp.poe_api` which strips wiki markup and unwraps descriptions to flat strings before feeding PoB2's Lua importer.
2. **Cold Boot Latency:**
   - Container start takes ~6.6 seconds. Must be kept persistent as a daemon; cannot be spawned on-demand per Ctrl+C event.
3. **Warm Simulation Latency:**
   - ~1.4 seconds per item simulation. This is too slow for a synchronous in-game Ctrl+C HUD overlay (which expects <50ms feedback), but ideal for a background asynchronous advisor.

---

## Verdict: PARTIAL (Viable as Asynchronous Advisor, Not Synchronous Replacer)

### Recommendation for Live Ctrl+C Integration:
- **Do NOT replace companion's native parser and rules engine.**
- **Dual-tier architecture:**
  - **Tier 1 (Instant / Synchronous, <10ms):** Existing `poe2-companion` rules engine evaluates clipboard immediately (Fubgun campaign rules, build-breaker checks, resistance delta, attribute sufficiency).
  - **Tier 2 (Deep Background Audit, ~1.4s):** PoB2 MCP engine running in persistent background daemon validates exact PoB2 internal calculations (exact TotalEHP, full passive tree interaction, multi-hit defense breakdown) and streams non-blocking updates.
