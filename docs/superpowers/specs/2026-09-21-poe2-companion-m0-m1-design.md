# Design Specification: Hermes PoE2 Companion (M0 & M1)

**Status:** Proposed  
**Date:** 2026-09-21  
**Scope:** M0 (Source Freeze & Validation) & M1 (State Foundation)  
**Target Build:** Fubgun 0.5.5 Flameblast / Oil Grenade  
**Reference:** `POE2_Hermes_Companion_Blueprint_v2.md`  

---

## 1. Context and Goals

This design defines the implementation of **M0** and **M1** for the personal-use **Hermes PoE2 Companion** at `C:\Projects\poe2-companion`.

The companion is a personal, local AI journey director and advisor for Path of Exile 2. It is **not** a bot and does not control the game.
This initial run is strictly limited to:
- **M0 — Freeze and Validate Sources**: Extract, validate, normalize, and manifest the 9 Fubgun `.build` files from `C:\Users\Fikri\Downloads\0.5.5 Fubgun Flameblast Oil Grenade.zip`.
- **M1 — State Foundation**: Establish the per-character persistent state store with atomic crash-safe writes, field provenance, verification enums, single-writer locking, backup rotation, and schema migration support.
- **Hard No-Input Compliance**: Establish static code inspection to ensure the companion contains no game-input automation libraries or API hooks.

All M2+ features (Client.txt watcher, process watcher, screenshots, vision/OCR, GGG API/OAuth, notifications, live monitoring, audit workflows) are explicitly out of scope for this run.

---

## 2. Technical Stack and Architecture Principles

### 2.1 Dependencies
- **Runtime:**
  - Python 3.11+
  - `pydantic` >= 2.0 (strictly typed models, data validation, serialization)
  - `PyYAML` >= 6.0 (safe YAML parsing for `guide_rules.yaml` via `yaml.safe_load`)
- **Development & Testing:**
  - `pytest`
  - `pytest-cov`
- **CLI:**
  - Standard library `argparse` (modular subcommands: `sources`, `state`).

### 2.2 Simplicity Rules
- Pure local file-based architecture. No SQLite, SQLAlchemy, FastAPI, Docker, Redis, or microservices.
- No dependency injection containers or excessive abstractions.

### 2.3 Compliance and Safety Rules
- Unattended companion daemon and modules must never import or invoke game-control or input-simulation mechanisms:
  `pyautogui`, `pynput`, `keyboard`, `mouse`, `SendInput`, `keybd_event`, `mouse_event`, `cua-driver` input, memory-reading or DLL injection APIs.
- Enforced via static AST/import scanner in the test suite.

---

## 3. Detailed Component Design

### 3.1 Project Directory Layout
```text
C:\Projects\poe2-companion\
├── pyproject.toml
├── README.md
├── POE2_Hermes_Companion_Blueprint_v2.md
├── companion\
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── compliance\
│   │   ├── __init__.py
│   │   └── no_input_guard.py
│   ├── sources\
│   │   ├── __init__.py
│   │   ├── models_raw.py
│   │   ├── models_normalized.py
│   │   ├── interval.py
│   │   ├── unpacker.py
│   │   ├── validator.py
│   │   ├── manifest.py
│   │   └── reporter.py
│   └── state\
│       ├── __init__.py
│       ├── schema.py
│       ├── provenance.py
│       ├── store.py
│       ├── lock.py
│       ├── backup.py
│       └── migrations.py
├── data\
│   ├── source\
│   │   ├── builds\               # Immutable raw .build files
│   │   ├── manifest.json         # Generated deterministic source manifest
│   │   └── guide_rules.yaml      # Initial Fubgun rules
│   └── reports\
│       ├── m0_anomaly_report.json
│       └── m0_anomaly_report.md
├── runtime\                      # Local runtime storage (gitignored except .gitkeep)
│   ├── active_character.json
│   ├── characters\
│   │   └── <character_id>.json
│   └── backups\
│       └── <character_id>\
├── tests\
│   ├── __init__.py
│   ├── conftest.py
│   ├── compliance\
│   │   └── test_no_input_guard.py
│   ├── sources\
│   │   ├── test_interval.py
│   │   ├── test_unpacker.py
│   │   ├── test_validator.py
│   │   ├── test_manifest.py
│   │   └── test_raw_vs_normalized.py
│   └── state\
│       ├── test_schema.py
│       ├── test_provenance.py
│       ├── test_store_isolation.py
│       ├── test_atomic_write.py
│       ├── test_single_writer.py
│       ├── test_backup_recovery.py
│       └── test_migrations.py
└── docs\
    └── superpowers\
        └── specs\
            └── 2026-09-21-poe2-companion-m0-m1-design.md
```

---

### 3.2 M0: Source Validation & Normalization Design

#### 3.2.1 Raw vs Normalized Models
1. **RawBuild**:
   - Matches official PoE2 `.build` JSON format.
   - Keeps unknown/extra fields using `model_config = ConfigDict(extra="allow")`.
   - Preserves raw `additional_text` without mutation.
   - Raw passive entries are preserved as extracted lists to allow audit of exact duplicates.
2. **NormalizedBuild**:
   - Structured representation for companion logic.
   - `level_interval` normalized via `IntervalShape` enum (`EXPLICIT_RANGE`, `SINGLE_UINT_UNSUPPORTED`, `UNRESTRICTED`).
   - Passive logical identity modeled as `(passive_id, weapon_set_context)`.
   - `weapon_set_context` normalized to:
     - `None` / omitted -> `DEFAULT_OR_SHARED`
     - `1` -> `SPECIALISATION_1`
     - `2` -> `SPECIALISATION_2`
     - `0` -> `UNKNOWN_RESERVED`
   - Aggregates duplicate passives while recording occurrences count, distinct intervals, and original indices.

#### 3.2.2 Snapshots Verification
The 9 expected stages in the Fubgun archive:
1. `lvl 1-14`
2. `lvl 15-32`
3. `lvl 33-51`
4. `lvl 52 Swap`
5. `lvl 53-68`
6. `lvl 85`
7. `Endgame`
8. `Mageblood`
9. `DoT Cap`

If any stage is missing or an extraneous file exists in the archive, validator flags it explicitly.

#### 3.2.3 Special Anomalies & Annotations
- **Cast on Dodge**: Meta-gem anomaly. The validator inspects all skills and supports. When `Cast on Dodge` is encountered, it records snapshot name, raw ID, `level_interval` (e.g. `[58, 100]`), and flags it as `SOURCE_ANNOTATION: meta-gem unsupported by official planner`.
- **Markup in `additional_text`**: Checked and recorded if present.
- **Weapon-set context duplicates**: Logged in detail.

#### 3.2.4 Source Manifest (`data/source/manifest.json`)
Deterministic JSON file:
- `manifest_version`: "1.0"
- `target_game_version`: "0.5.5"
- `build_name`: "Fubgun Flameblast Oil Grenade"
- `source_archive`: path, size, sha256
- `extracted_at`: ISO timestamp
- `files`: list of objects with:
  - `logical_stage`
  - `original_filename`
  - `stored_path`
  - `sha256`
  - `byte_size`
  - `validation_status` (PASS / ANOMALIES / FAIL)
  - `anomalies`: list of anomaly tags

---

### 3.3 M1: Character State Foundation Design

#### 3.3.1 Provenance and Verification
Every observable state fact is wrapped in `ProvenancedField[T]`:
```python
class VerificationState(str, Enum):
    VERIFIED = "VERIFIED"
    CORROBORATED = "CORROBORATED"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    CONFLICTING = "CONFLICTING"

class ProvenancedField(BaseModel, Generic[T]):
    value: Optional[T] = None
    source: Optional[str] = None
    observed_at: Optional[datetime] = None
    verification: VerificationState = VerificationState.UNKNOWN
    stale_after: Optional[str] = None
    evidence_ref: list[str] = Field(default_factory=list)
```

#### 3.3.2 CharacterState v2 Schema
Root model contains:
- `schema_version`: Literal["2.0"]
- `character`: id, name, class_name, ascendancy, level
- `game_version`: default "0.5.5"
- `journey`: area, progression_phase, target_variant, flags
- `transition`: level_52 transition status and requirements
- `equipment`: set1, set2, set3, helmet, body_armour, gloves, boots, amulet, ring1, ring2, belt, charms
- `skills`: entries, source_state
- `passives`: allocated, specialisations (set1, set2, set3), quest_stats (list)
- `visible_stats`: life, mana, spirit, armour, evasion, fire_res, cold_res, lightning_res, chaos_res
- `resources`: gold, gcp
- `audit`: gear_last_completed, skill_last_completed, passive_checkpoint_last_completed

#### 3.3.3 File Store & Per-Character Isolation
- Characters stored at `runtime/characters/<safe_char_id>.json`.
- `runtime/active_character.json` points to the currently active character ID and file path.
- Sanitization helper prevents path traversal (`..` or invalid characters in ID).

#### 3.3.4 Single-Writer Enforcement
- File lock mechanism: `runtime/state.lock`.
- On Windows: Uses `msvcrt.locking` on an open lockfile or non-blocking atomic file open.
- When writer process starts, it holds the exclusive lock. If another process tries to acquire, `StateLockError` is raised immediately.
- Context manager `StateLock`:
  ```python
  with StateLock(lock_path):
      # write state
  ```

#### 3.3.5 Atomic Writes & Rolling Backups
- Atomic write flow:
  1. Serialize Pydantic model to formatted JSON string.
  2. Write to temp file `runtime/characters/<safe_char_id>.tmp.<uuid>`.
  3. `flush()` and `os.fsync(fileno)`.
  4. Rotate current file (if exists) into `runtime/backups/<safe_char_id>/state.<timestamp>.bak` (keep max 3).
  5. `os.replace(tmp_path, final_path)`.
- If final file is corrupted, store provides `recover_from_backup(character_id)`.

#### 3.3.6 Lightweight Schema Migrations
- `migrations.py` contains registry: `MIGRATION_REGISTRY: dict[str, Callable[[dict], dict]]`.
- When loading JSON:
  - If `schema_version == "2.0"` -> pass directly to `CharacterState.model_validate(data)`.
  - If older known version -> sequentially apply upgrade functions.
  - If unknown future version -> raise `UnsupportedSchemaVersionError`.

---

### 3.4 Compliance Guard Design

`companion/compliance/no_input_guard.py`:
- Scans Python files in `companion/` using `ast.parse`.
- Collects:
  - `Import` and `ImportFrom` modules
  - `Call` names and attribute lookups
- Prohibited tokens:
  - Modules: `pyautogui`, `pynput`, `keyboard`, `mouse`, `ctypes.windll.user32.SendInput`
  - Symbols: `SendInput`, `keybd_event`, `mouse_event`
  - Patterns: memory injection, dll injection, `cua_driver` input
- If any forbidden token is found in unattended packages, returns failure with file, line number, and offending symbol.

---

### 3.5 CLI Design

`companion/cli.py` using `argparse`:
- `python -m companion sources unpack --archive <path>` (defaults to `C:\Users\Fikri\Downloads\0.5.5 Fubgun Flameblast Oil Grenade.zip`)
- `python -m companion sources validate [--report]`
- `python -m companion sources inspect <stage>`
- `python -m companion state init --character-id <id> --name <name>`
- `python -m companion state inspect [--character-id <id>]`

---

## 4. Verification and Test Plan

### 4.1 Unit Tests
- `test_no_input_guard.py`: Passes on clean codebase; raises violation on synthetic test files importing forbidden libraries.
- `test_interval.py`: Verifies `None`, `[0, 100]`, negative bounds, `min > max`, lengths != 2, and single uint.
- `test_validator.py` & `test_raw_vs_normalized.py`:
  - Validates all 9 `.build` files extracted from the actual zip.
  - Validates passive deduplication preservation with `(passive_id, weapon_set_context)`.
  - Detects `Cast on Dodge` meta-gem anomaly accurately.
- `test_manifest.py`: Ensures manifest hash calculation is deterministic and matches byte-for-byte on repeat runs.
- `test_store_isolation.py`: Two characters never collide or overwrite each other.
- `test_atomic_write.py`: Confirms temporary file cleanup and crash-safety.
- `test_single_writer.py`: Proves second writer cannot acquire lock while first writer holds it.
- `test_backup_recovery.py`: Corrupting current state successfully restores from newest backup.
- `test_migrations.py`: Old schema version upgraded; future schema version rejected cleanly.

### 4.2 Integration Smoke Test
1. Run `python -m companion sources unpack`.
2. Run `python -m companion sources validate --report`.
3. Run `python -m companion state init --character-id gemling_01 --name "FikriGemling"`.
4. Run `python -m companion state inspect`.
5. Run full pytest suite with 100% pass rate.
