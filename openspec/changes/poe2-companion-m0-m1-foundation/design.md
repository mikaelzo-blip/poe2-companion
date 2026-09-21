# Design: PoE2 Companion M0–M1 Foundation

## Context

The PoE2 Hermes Companion is a personal, read-only AI journey director and tactical advisor for Path of Exile 2. It tracks character progression against authoritative build guides (specifically Fubgun 0.5.5 Flameblast / Oil Grenade Mercenary / Gemling Legionnaire).

As established in `POE2_Hermes_Companion_Blueprint_v2.md` and the initial M0–M1 design (`docs/superpowers/specs/2026-09-21-poe2-companion-m0-m1-design.md`), this system must never control or automate game actions. Note that early brainstorm ideas in `IDEA.md` (such as an injected DirectX/Vulkan overlay and local SQLite cache) conflict with Blueprint v2; `IDEA.md` is superseded and Blueprint v2 remains authoritative.

Before downstream reasoning (M2+) or live observation (M5+) can function reliably, the foundation requires:
1. Deterministic validation, ZIP slip protection, and immutable storage of the nine expected pinned Fubgun 0.5.5 build snapshots from the supplied source archive (M0).
2. Crash-safe, verified per-character persistent state storage with cross-process single-writer enforcement, conservative character ID safety, atomic writing, and safe backup copy ordering (M1).
3. Static defense-in-depth no-input compliance checking enforced via lightweight AST inspection.
4. Repository hygiene rules established prior to implementation.

See `proposal.md` for motivation and high-level scope.

## Goals / Non-Goals

**Goals:**
- Unpack, validate, and hash the nine expected pinned Fubgun 0.5.5 `.build` files from the source archive into immutable storage (`data/source/builds/`), protecting against ZIP slip attacks (rejecting `../`, absolute paths, Windows drive paths, and paths escaping the target root).
- Enforce strict separation between raw input representations (`RawBuild*`) and normalized models (`NormalizedBuild*`), preserving unknown fields and raw source occurrences without data loss.
- Validate `level_interval` conservatively (supporting absent, `[min, max]`, and single unsigned integers as unresolved shapes; rejecting invalid bounds).
- Preserve passive logical identity as `(passive_id, weapon_set_context)` to prevent invalid deduplication across weapon sets.
- Annotate known source anomalies (e.g. `Cast on Dodge` meta-gem) and generate a canonical, byte-for-byte deterministic `data/source/manifest.json` (excluding wall-clock run timestamps like `extracted_at`) alongside diagnostic anomaly reports.
- Define a schema and initial structure for `data/source/guide_rules.yaml` with explicit provenance metadata (`BLUEPRINT_V2` vs `PENDING_SOURCE_VERIFICATION`), without inventing unverified rules or building an executable rule engine.
- Implement `CharacterState v2` Pydantic models with `ProvenancedField[T]` and semantic verification enums.
- Implement isolated per-character JSON file storage in `runtime/characters/<char_id>.json`, using conservative character ID validation (`InvalidCharacterIdError`) and `runtime/active_character.json` tracking via atomic writes.
- Enforce cross-process single-writer access via Windows standard file locking (`msvcrt.locking` with `LK_NBLCK` on `runtime/state.lock`) held across the entire state mutation transaction.
- Implement crash-safe atomic writes and safe backup ordering (write temp → flush + `os.fsync` → copy valid state to backup → atomic `os.replace` → prune old backups beyond max 3).
- Implement lightweight schema versioning (`schema_version: "2.0"`) and migration upgrade dispatch.
- Implement a static AST defense-in-depth compliance check (`companion/**/*.py`) rejecting forbidden input-simulation libraries and known API patterns (direct, `from`, aliased imports, and native call tokens).
- Establish a minimal `.gitignore` policy before implementation to keep local/generated state out of version control while tracking authoritative assets.
- Provide minimal CLI commands via standard-library `argparse`.

**Non-Goals:**
- M2 eligibility engine, progression phase resolution, or passive/skill delta generation.
- M3 persistent level-52 transition evaluation or executable rule engines.
- M4 objective engine.
- M5+ live game watchers, `Client.txt` tailing, process monitoring, screenshots, OCR, or GGG API integration.
- Distributed locking, background daemon services, databases (SQLite/Postgres), Docker, Redis, or web dashboards.
- Injected overlays or memory manipulation (concepts from `IDEA.md` are superseded).
- Arbitrary numeric/LLM confidence percentages (only semantic verification states are permitted).
- Lossy character ID sanitization or silent filename collapsing.

## Decisions

### 1. Data Model Architecture: Raw vs. Normalized vs. Runtime State
- **Choice**: Separate three distinct model hierarchies:
  1. `companion.sources.models_raw`: Pydantic models using `ConfigDict(extra="allow")` mirroring official `.build` JSON schemas exactly without loss.
  2. `companion.sources.models_normalized`: Clean, typed representations where intervals and weapon-set contexts are normalized and passive duplicates are indexed.
  3. `companion.state.schema`: Runtime character models wrapping facts in `ProvenancedField[T]`.
- **Rationale**: Keeps raw source bytes immutable. Normalization bugs can be fixed without corrupting or modifying original source files.
- **Alternatives Considered**: Direct in-place normalization during ingestion (rejected: destroys raw auditability and extra fields).

### 2. Conservative `level_interval` Handling
- **Choice**: Model interval shapes as:
  - `None` / omitted → unrestricted.
  - Two-element list `[min, max]` where `0 <= min <= max` → explicit range.
  - Single non-negative integer `uint` → preserved as a valid shape with status `UNRESOLVED_SINGLE_UINT`.
  - Any negative number, inverted range (`min > max`), or non-integer → validation error.
- **Rationale**: Across the 9 Fubgun snapshots, all 380 interval entries are explicit `[min, max]`. Single integers are permitted by the generic official schema but have undefined semantics in the planner; preserving them without inventing meaning avoids false assumptions. M2 eligibility checks (`ACTIVE`, `FUTURE`, `EXPIRED`) are strictly deferred.
- **Alternatives Considered**: Treating single uint as `[val, 100]` or `[val, val]` (rejected: invents semantics contrary to Blueprint v2).

### 3. Passive Identity and Weapon-Set Context
- **Choice**: Passive compound key is `(passive_id, weapon_set_context)`. Weapon-set context mapping:
  - Omitted / `None` → `DEFAULT_OR_SHARED`
  - `1` → `SPECIALISATION_1`
  - `2` → `SPECIALISATION_2`
  - `0` → `UNKNOWN_RESERVED`
  - Other values → validation warning.
- **Rationale**: In the Fubgun snapshots, 13 passives in Mageblood and 12 in DoT Cap appear in multiple weapon-set contexts. Deduplicating by `passive_id` alone destroys build validity.
- **Alternatives Considered**: Deduplicating on `passive_id` alone (rejected: violates Blueprint v2 Section 8.2).

### 4. ZIP Slip Protection during Archive Unpacking
- **Choice**: `companion/sources/unpacker.py` inspects each member in the source archive before extracting:
  - Validates that normalized member paths contain no `..` traversal components.
  - Rejects absolute paths (e.g. `/path` or `\path`) and Windows drive-qualified paths (e.g. `C:\path`).
  - Verifies that `os.path.commonpath([target_dir, resolved_member_path]) == target_dir`.
  - Materializes only the expected `.build` files into `data/source/builds/`.
- **Rationale**: Prevents arbitrary file overwrite or write outside the intended raw source root if an archive is maliciously crafted.
- **Alternatives Considered**: Direct `ZipFile.extractall()` without per-entry path validation (rejected: vulnerable to ZIP slip).

### 5. Deterministic Canonical Source Manifest
- **Choice**: Canonical `data/source/manifest.json` contains:
  - `manifest_version`: "1.0"
  - `target_game_version`: "0.5.5"
  - `build_name`: "Fubgun Flameblast Oil Grenade"
  - `tool_version`: string version of companion unpacker/validator
  - `files`: sorted list of snapshots by progression stage containing `logical_stage`, `filename`, `sha256`, `byte_size`, and `validation_status`.
  Wall-clock or operational run timestamps (e.g. `extracted_at`) are excluded from `manifest.json` and placed only in `data/reports/m0_anomaly_report.json` and `.md`. Keys and list entries are serialized with deterministic sorting and indentation.
- **Rationale**: Identical source archive bytes and tool version must yield byte-for-byte reproducible canonical manifest outputs across runs.
- **Alternatives Considered**: Storing `extracted_at` in canonical manifest (rejected: breaks deterministic output requirements).

### 6. Guide Rules Schema and Provenance Integrity
- **Choice**: Create `data/source/guide_rules.yaml` with an explicit schema and provenance metadata:
  - Rules derived strictly from Blueprint v2 are tagged with `provenance: BLUEPRINT_V2`.
  - Rules referencing external written Fubgun guide details (which are not yet frozen in the repo) are marked `status: PENDING_SOURCE_VERIFICATION`.
  - No executable rule engine is built in M0/M1; rules remain declarative data.
- **Rationale**: Avoids hallucinating or encoding unverified external guide rules while establishing the required schema foundation.
- **Alternatives Considered**: Hardcoding unverified Fubgun gameplay rules (rejected: violates source integrity).

### 7. Character ID Filename Safety
- **Choice**: Reject invalid character IDs rather than using lossy sanitization.
  - Allowed format: regex `^[a-zA-Z0-9_-]{1,64}$` (non-empty alphanumeric characters, hyphens, underscores; max 64 chars).
  - Any ID containing path separators (`/`, `\`), traversal (`..`), spaces, or special characters immediately raises `InvalidCharacterIdError`.
  - The original character ID is preserved inside the `CharacterState` model.
- **Rationale**: Lossy sanitization (e.g. replacing punctuation with underscores) risks collision where distinct IDs (like `test.1` and `test/1`) collapse into the same filename (`test_1.json`). Conservative rejection is safer and unambiguous.
- **Alternatives Considered**: Regex substitution of illegal characters with underscores (rejected: prone to collision).

### 8. Cross-Process Single-Writer Local File Locking (`msvcrt.locking`)
- **Choice**: Windows standard-library file locking via `msvcrt.locking`:
  - Lock target: `runtime/state.lock`.
  - On open: open in `r+b` mode (or `w+b` if not present). Ensure the lock file contains at least 1 byte (writing `b"\x00"` and flushing if 0 bytes).
  - Seek: `seek(0, os.SEEK_SET)` before locking.
  - Lock: `msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)` to lock exactly byte 0 in non-blocking mode.
  - Duration: The file descriptor remains open and locked for the entire logical state mutation transaction (covering serialization, temp write, sync, backup copy, atomic replace, and backup pruning).
  - Cleanup: In a `finally` block, seek to 0, unlock with `msvcrt.LK_UNLCK`, and reliably close the file descriptor.
  - Contention: Raises `StateLockError` immediately without altering state.
  - Verification: Tested using separate child processes (`subprocess` or `multiprocessing`) to prove cross-process mutual exclusion.
- **Rationale**: Built-in Windows file locking without third-party dependencies, guaranteeing single-writer isolation across processes.
- **Alternatives Considered**: Third-party libraries like `filelock` (rejected: standard library `msvcrt` is sufficient and introduces zero extra dependencies).

### 9. Crash-Safe Atomic Writes and Safe Backup Ordering
- **Choice**: Ordered atomic persistence sequence:
  1. Serialize new state into formatted JSON bytes.
  2. Write to a temporary file in the same directory: `runtime/characters/<char_id>.tmp.<uuid>`.
  3. Flush user-space buffer and call `os.fsync(f.fileno())`.
  4. If a current canonical state file exists and is valid, COPY it to `runtime/backups/<char_id>/state.<timestamp>.bak` using a safe backup write procedure. The canonical file is NOT moved or deleted before replacement.
  5. Atomically swap destination file: `os.replace(temp_path, canonical_path)`.
  6. Only after successful canonical replacement, prune old backups beyond the retention limit (max 3 backups).
  7. If existing canonical state is corrupt or unreadable, it is NEVER copied to backup, preserving existing valid backups.
  8. `runtime/active_character.json` uses the same atomic-write primitive (temp write, flush, fsync, `os.replace`).
- **Rationale**: Eliminates the crash window in the previous design where moving the canonical file prior to replacement left no canonical file on disk during a mid-flight crash.
- **Alternatives Considered**: Moving canonical file before replacement (rejected: creates missing-file crash window).

### 10. Semantic Verification over Numeric Confidence
- **Choice**: `VerificationState` enum with values: `VERIFIED`, `CORROBORATED`, `SINGLE_SOURCE`, `STALE`, `UNKNOWN`, `CONFLICTING`.
- **Rationale**: LLM-generated percentage confidences (e.g. 87%) are uncalibrated and misleading. Semantic states reflect actual verification mechanisms (e.g. multi-source match vs single capture).
- **Alternatives Considered**: Floating-point confidence score (rejected: uncalibrated).

### 11. Static No-Input AST Guard (Defense-in-Depth)
- **Choice**: `companion/compliance/no_input_guard.py` acts as a lightweight defense-in-depth static compliance check:
  - Scope: `companion/**/*.py`.
  - Excluded paths: `.venv/`, test fixtures, `docs/`, `data/`, `runtime/`, and OpenSpec artifacts.
  - Detects:
    - Direct module imports: `import pyautogui`, `import pynput`, `import keyboard`, `import mouse`
    - From-imports: `from pynput import mouse`, `from ctypes.windll.user32 import SendInput`
    - Aliased imports: `import pyautogui as pag`, `from pynput.keyboard import Controller as KCtrl`
    - Prohibited native call tokens/attributes: `SendInput`, `keybd_event`, `mouse_event`
  - Wording: Clearly documented as an enforcement of prohibited dependencies and known API patterns at static-analysis time, not an absolute mathematical guarantee of zero game-input capability.
- **Rationale**: Catches accidental or intentional introduction of game automation libraries early in CI/test runs without heavy runtime overhead.
- **Alternatives Considered**: General security analyzer / bytecode interception (rejected: over-engineered for personal-use compliance).

### 12. Repository Hygiene Policy
- **Choice**: Define a minimal `.gitignore` before implementation:
  - Excludes Python artifacts: `__pycache__/`, `*.py[cod]`, `.venv/`
  - Excludes test and coverage artifacts: `.pytest_cache/`, `.coverage`, `htmlcov/`
  - Excludes environment variables: `.env`
  - Excludes runtime character state and backups: `runtime/characters/`, `runtime/backups/`, `runtime/*.lock`, `runtime/*.json`, `*.tmp.*`
  - Excludes future screenshot caches
  - Tracks: `POE2_Hermes_Companion_Blueprint_v2.md`, `openspec/`, `tests/`, `companion/`, and `data/source/` (including raw `.build` files and `manifest.json`).
- **Rationale**: Prevents transient runtime data and local venv files from polluting git while keeping all authoritative source references versioned.

## Risks / Trade-offs

- **[Risk] Crash during state update** → **Mitigation**: Safe backup copy occurs before replacement, same-directory `os.replace` guarantees atomic rename on Windows, and old backups are pruned only after replacement. Corrupt files never overwrite valid backups.
- **[Risk] Path traversal in character ID** → **Mitigation**: Conservative regex format (`^[a-zA-Z0-9_-]{1,64}$`) rejects traversal sequences (`..`, `/`, `\`) with `InvalidCharacterIdError` rather than lossy sanitization.
- **[Risk] Cross-process lock contention** → **Mitigation**: `msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)` on non-empty lock file held for entire mutation transaction; raises `StateLockError` immediately on contention. Tested with separate processes.
- **[Risk] Malicious or corrupt archive containing traversing paths (ZIP Slip)** → **Mitigation**: Archive extraction strictly validates member path resolution against extraction target directory before writing.
- **[Risk] Non-deterministic manifest output** → **Mitigation**: Wall-clock timestamps (`extracted_at`) are excluded from canonical manifest and stored only in anomaly reports; manifest uses deterministic key ordering.
- **[Risk] Unverified external guide rules** → **Mitigation**: Schema requires provenance metadata (`BLUEPRINT_V2` or `PENDING_SOURCE_VERIFICATION`); no executable rule engine in M0/M1.

## Migration Plan

1. Create minimal `.gitignore` to establish clean repository hygiene.
2. Initialize project directories (`companion/`, `data/source/builds/`, `data/reports/`, `runtime/characters/`, `runtime/backups/`, `tests/`).
3. Mark `IDEA.md` as superseded by Blueprint v2.
4. Unpack source archive with ZIP slip validation into `data/source/builds/`.
5. Validate sources, generate deterministic canonical `data/source/manifest.json` and anomaly reports.
6. Author `data/source/guide_rules.yaml` skeleton with provenance tags.
7. Character state starts at schema version `2.0`. Future versions will register upgrade callables in `companion/state/migrations.py`.

## Open Questions / Conflicts

- **Blueprint v2 vs `IDEA.md`**:
  - `IDEA.md` described early brainstorm ideas (injected overlay, SQLite cache) that contradict Blueprint v2's read-only file-based architecture.
  - *Resolution*: `IDEA.md` is marked `SUPERSEDED — DO NOT USE FOR IMPLEMENTATION`. Blueprint v2 is authoritative.
- **Blueprint v2 vs Prior Design on Rule Format**:
  - Blueprint v2 specifies creating initial `guide_rules.yaml` in M0 while deferring rule execution to M3. The repository lacks the frozen written Fubgun guide text.
  - *Resolution*: M0 creates a declarative skeleton with explicit provenance (`BLUEPRINT_V2` or `PENDING_SOURCE_VERIFICATION`). No rule engine is built in M0/M1.
- **Single-uint interval semantics**:
  - Generic official schema allows single uints, but planner semantics are undefined.
  - *Resolution*: Preserved as `UNRESOLVED_SINGLE_UINT` shape without inventing semantics.
- **Weapon-set value `0`**:
  - *Resolution*: Retain as `UNKNOWN_RESERVED` as mandated by Blueprint v2 Section 8.3 until real source evidence defines its meaning.
