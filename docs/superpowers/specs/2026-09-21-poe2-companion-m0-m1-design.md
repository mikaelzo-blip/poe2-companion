# Design Specification: Hermes PoE2 Companion (M0 & M1)

**Status:** Proposed (Revised)  
**Date:** 2026-09-21  
**Scope:** M0 (Source Freeze & Validation) & M1 (State Foundation)  
**Target Build:** Fubgun 0.5.5 Flameblast / Oil Grenade  
**Reference:** `POE2_Hermes_Companion_Blueprint_v2.md`  

---

## 1. Context and Goals

This design defines the implementation of **M0** and **M1** for the personal-use **Hermes PoE2 Companion** at `C:\Projects\poe2-companion`.

The companion is a personal, local AI journey director and advisor for Path of Exile 2. It is **not** a bot and does not control the game. Early brainstorm notes in `IDEA.md` (such as an injected DirectX/Vulkan overlay and SQLite cache) conflict with Blueprint v2 and are marked `SUPERSEDED — DO NOT USE FOR IMPLEMENTATION`. Blueprint v2 remains authoritative.

This initial foundation run is strictly limited to:
- **Repository Hygiene**: Establish a minimal `.gitignore` before implementation.
- **M0 — Freeze and Validate Sources**: Extract the nine expected pinned Fubgun 0.5.5 build snapshots from the supplied source archive (`C:\Users\Fikri\Downloads\0.5.5 Fubgun Flameblast Oil Grenade.zip`) with ZIP slip protection, validate, normalize, and manifest them deterministically.
- **M1 — State Foundation**: Establish the per-character persistent state store with atomic crash-safe writes, safe backup copy ordering, field provenance, verification enums, cross-process single-writer locking via `msvcrt.locking`, conservative character ID validation, and schema migration support.
- **Defense-in-Depth No-Input Compliance**: Establish static AST code inspection across `companion/**/*.py` to enforce the project's prohibited input/control dependencies and known API patterns at static-analysis time.

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
- **CLI & System:**
  - Standard library `argparse` (modular subcommands: `sources`, `state`).
  - Standard library `msvcrt` (Windows single-writer file locking).

### 2.2 Simplicity Rules
- Pure local file-based architecture. No SQLite, SQLAlchemy, FastAPI, Docker, Redis, or microservices.
- No dependency injection containers or excessive abstractions.

### 2.3 Compliance and Safety Rules
- Defense-in-depth static compliance check: companion modules must never import or invoke game-control or input-simulation mechanisms:
  `pyautogui`, `pynput`, `keyboard`, `mouse`, `SendInput`, `keybd_event`, `mouse_event`, `cua-driver` input, memory-reading or DLL injection APIs.
- Enforced via lightweight AST inspection on `companion/**/*.py` in the test suite, excluding virtual environments, test fixtures, docs, data, runtime, and OpenSpec artifacts.

---

## 3. Detailed Component Design

### 3.1 Project Directory Layout
```text
C:\Projects\poe2-companion\
├── .gitignore
├── pyproject.toml
├── README.md
├── POE2_Hermes_Companion_Blueprint_v2.md
├── IDEA.md                           # Marked SUPERSEDED
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
│   │   ├── manifest.json         # Byte-for-byte deterministic source manifest (no run timestamps)
│   │   └── guide_rules.yaml      # Initial schema/skeleton with explicit provenance tags
│   └── reports\
│       ├── m0_anomaly_report.json
│       └── m0_anomaly_report.md
├── runtime\                      # Local runtime storage (gitignored except .gitkeep)
│   ├── active_character.json
│   ├── state.lock
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
   - Matches PoE2 `.build` JSON format.
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

#### 3.2.2 Snapshots Verification and ZIP Slip Protection
The nine expected pinned stages in the Fubgun 0.5.5 archive:
1. `lvl 1-14`
2. `lvl 15-32`
3. `lvl 33-51`
4. `lvl 52 Swap`
5. `lvl 53-68`
6. `lvl 85`
7. `Endgame`
8. `Mageblood`
9. `DoT Cap`

The unpacker validates each ZIP entry against traversal sequences (`../`), absolute paths, Windows drive paths, and target directory escape before extraction. Only expected `.build` files are written to `data/source/builds/`. If any required stage is missing or an extraneous file exists in the archive, the validator flags it explicitly.

#### 3.2.3 Special Anomalies & Annotations
- **Cast on Dodge**: Meta-gem anomaly. The validator inspects all skills and supports. When `Cast on Dodge` is encountered, it records snapshot name, raw ID, `level_interval` (e.g. `[58, 100]`), and flags it as `SOURCE_ANNOTATION: meta-gem unsupported by official planner`.
- **Markup in `additional_text`**: Checked and recorded if present.
- **Weapon-set context duplicates**: Logged in detail.

#### 3.2.4 Source Manifest (`data/source/manifest.json`)
Deterministic canonical JSON file (byte-for-byte identical across runs for identical source bytes):
- `manifest_version`: "1.0"
- `target_game_version`: "0.5.5"
- `build_name`: "Fubgun Flameblast Oil Grenade"
- `tool_version`: "0.1.0"
- `files`: sorted list of objects by progression stage with:
  - `logical_stage`
  - `filename`
  - `sha256`
  - `byte_size`
  - `validation_status` (PASS / ANOMALIES / FAIL)
*(Note: Wall-clock run timestamps like `extracted_at` are excluded from the canonical manifest and recorded only in `data/reports/m0_anomaly_report.json` and `.md`.)*

#### 3.2.5 Guide Rules Integrity (`data/source/guide_rules.yaml`)
- Provides schema and skeleton.
- Explicit provenance: `provenance: BLUEPRINT_V2` for items derived from Blueprint v2; items requiring external guide text are tagged `status: PENDING_SOURCE_VERIFICATION`.
- No executable rule engine is built in M0/M1.

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

#### 3.3.3 File Store, Isolation & Character ID Safety
- Characters stored at `runtime/characters/<character_id>.json`.
- Character ID validation: Conservative allowed pattern `^[a-zA-Z0-9_-]{1,64}$`. Any invalid characters or path separators raise `InvalidCharacterIdError` (no lossy sanitization). Original character ID preserved inside model.
- `runtime/active_character.json` points to the currently active character ID and file path.

#### 3.3.4 Cross-Process Single-Writer Enforcement
- Mechanism: Windows standard `msvcrt.locking` on `runtime/state.lock`.
- Lockfile guarantees at least 1 byte, seeks to byte 0, and acquires exclusive lock on 1 byte via `msvcrt.LK_NBLCK`.
- Lock is held across the entire state mutation transaction (serialization, temp write, sync, backup copy, atomic replace, and backup pruning).
- Unlocked in `finally` and file descriptor reliably closed.
- Contention raises `StateLockError` immediately without modifying state.
- Verified via multi-process tests (`multiprocessing` / `subprocess`).

#### 3.3.5 Crash-Safe Atomic Writes & Safe Backup Ordering
- Ordered persistence sequence:
  1. Serialize Pydantic model to formatted JSON bytes.
  2. Write to temp file `runtime/characters/<character_id>.tmp.<uuid>`.
  3. `flush()` and `os.fsync(fileno)`.
  4. If current canonical state exists and is valid, COPY current canonical file to `runtime/backups/<character_id>/state.<timestamp>.bak` using a safe backup procedure (never move or delete canonical file before replacement).
  5. Atomically replace: `os.replace(tmp_path, canonical_path)`.
  6. Only after successful replacement, prune old backups exceeding retention limit (max 3 backups).
  7. Corrupted or unreadable canonical files are never copied to backup, preserving good backups.
  8. `runtime/active_character.json` uses the same atomic-write primitive.
- Store provides `recover_from_backup(character_id)` to restore the most recent valid backup if canonical state is corrupted.

#### 3.3.6 Lightweight Schema Migrations
- `migrations.py` contains registry: `MIGRATION_REGISTRY: dict[str, Callable[[dict], dict]]`.
- When loading JSON:
  - If `schema_version == "2.0"` -> pass directly to `CharacterState.model_validate(data)`.
  - If older known version -> sequentially apply upgrade functions.
  - If unknown future version -> raise `UnsupportedSchemaVersionError`.

---

### 3.4 Compliance Guard Design (Defense-in-Depth)

`companion/compliance/no_input_guard.py`:
- Static AST defense-in-depth scanner across `companion/**/*.py`.
- Excludes `.venv/`, test fixtures, `docs/`, `data/`, `runtime/`, and OpenSpec artifacts.
- Detects:
  - Direct module imports (`import pyautogui`, `import pynput`, `import keyboard`, `import mouse`)
  - From-imports (`from pynput import mouse`, `from ctypes.windll.user32 import SendInput`)
  - Aliased imports (`import pyautogui as pag`, `from pynput.keyboard import Controller as KCtrl`)
  - Prohibited native call tokens / attributes (`SendInput`, `keybd_event`, `mouse_event`)
- If any forbidden token is found, raises verification failure detailing file, line number, and offending symbol.

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
- `test_no_input_guard.py`: Enforces prohibited dependencies and known API patterns at static-analysis time; verifies direct, from, and aliased imports and call tokens fail compliance; ignores excluded folders.
- `test_interval.py`: Verifies `None`, `[0, 100]`, negative bounds, `min > max`, lengths != 2, and single uint.
- `test_unpacker.py`: Tests valid extraction and malicious synthetic ZIP slip entries (`../`, absolute paths).
- `test_validator.py` & `test_raw_vs_normalized.py`:
  - Validates the nine expected pinned `.build` files extracted from the archive.
  - Validates passive deduplication preservation with `(passive_id, weapon_set_context)`.
  - Detects `Cast on Dodge` meta-gem anomaly accurately.
- `test_manifest.py`: Verifies byte-for-byte deterministic canonical manifest output without run timestamps.
- `test_store_isolation.py`: Tests distinct characters, character ID safety (`InvalidCharacterIdError`), and collision resistance.
- `test_atomic_write.py`: Confirms same-dir temp file, fsync, safe backup copy ordering, and atomic replace failure cleanup.
- `test_single_writer.py`: Proves second writer in a separate process cannot acquire lock while first writer holds it.
- `test_backup_recovery.py`: Corrupted canonical state successfully restores from newest backup; corrupt state never displaces backups.
- `test_migrations.py`: Old schema version upgraded; future schema version rejected cleanly.

### 4.2 Integration Smoke Test
1. Run `python -m companion sources unpack`.
2. Run `python -m companion sources validate --report`.
3. Run `python -m companion state init --character-id gemling_01 --name "FikriGemling"`.
4. Run `python -m companion state inspect`.
5. Run full pytest suite with 100% pass rate.
