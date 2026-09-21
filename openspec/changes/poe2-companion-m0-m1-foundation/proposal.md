# Proposal: PoE2 Companion M0–M1 Foundation

## Why

The PoE2 companion requires an authoritative, deterministic foundation of build reference data and crash-safe local character state before any decision logic (M2+) or live sensors (M5+) can be built. Establishing immutable source validation and verified state persistence now guarantees that future journey guidance relies on verified source facts rather than hallucinated or corrupted state.

## What Changes

This change implements milestones M0 and M1 as specified in Blueprint v2:

- **Repository Hygiene (Pre-Implementation)**:
  - Establish a minimal `.gitignore` policy excluding local and generated artifacts (`.venv/`, `__pycache__/`, `.pytest_cache/`, `.coverage`, `htmlcov/`, `.env`, `runtime/characters/`, `runtime/backups/`, `runtime/*.lock`, `runtime/*.json`, temporary atomic files `*.tmp.*`, and future screenshot cache) while preserving authoritative source `.build` files, OpenSpec artifacts, source manifests, tests, and Blueprint v2.

- **Source Ingestion & Validation (M0)**:
  - Extract and preserve the nine expected pinned Fubgun 0.5.5 build snapshots from the supplied source archive into an immutable raw directory.
  - Guard archive extraction with strict ZIP slip path-traversal validation, rejecting `../` traversal, absolute paths, Windows drive-qualified paths, and escaped target directories, materializing only expected `.build` files.
  - Separate raw build models (`RawBuild*`) from normalized representations (`NormalizedBuild*`), never mutating raw source bytes.
  - Generate a canonical, byte-for-byte deterministic `data/source/manifest.json` with SHA-256 hashes, file sizes, and validation statuses (omitting wall-clock run timestamps such as `extracted_at`; recording run timestamps only in anomaly reports).
  - Implement conservative `level_interval` parsing: validate absent, `[min, max]`, and single unsigned integers (preserved as valid source shape with unresolved semantics; no M2 eligibility resolution).
  - Preserve passive identity as `(passive_id, weapon_set_context)` to avoid improper deduplication across weapon sets.
  - Annotate known source anomalies (e.g., `Cast on Dodge` meta-gem) and preserve unknown fields with warnings.
  - Generate machine-readable and human-readable anomaly reports with operational execution metadata.
  - Define `data/source/guide_rules.yaml` schema/skeleton and source metadata without inventing unverified rules, tagging Blueprint v2 provenance explicitly and marking unverified guide items as `PENDING_SOURCE_VERIFICATION` (no rule engine in M0/M1).

- **Character State Foundation (M1)**:
  - Implement `CharacterState v2` Pydantic models with per-field provenance (`ProvenancedField[T]`).
  - Support semantic verification states (`VERIFIED`, `CORROBORATED`, `SINGLE_SOURCE`, `STALE`, `UNKNOWN`, `CONFLICTING`) without arbitrary LLM percentages.
  - Provide per-character JSON file storage in `runtime/characters/<char_id>.json` using a conservative allowed character-ID format (rejecting invalid IDs with `InvalidCharacterIdError` rather than lossy sanitization) and active character tracking (`runtime/active_character.json`).
  - Enforce cross-process single-writer access via Windows standard file locking (`msvcrt.locking` with `LK_NBLCK` on `runtime/state.lock`) held across the entire state mutation transaction.
  - Implement crash-safe atomic write and backup ordering: write same-directory temp file, flush + `os.fsync`, copy valid current state into rolling backup before replacement, atomically swap (`os.replace(temp, canonical)`), and prune old backups beyond bounded retention count (max 3) only after successful canonical replacement. Ensure corrupt/unreadable canonical state never displaces good backups.
  - Apply the same atomic-write primitive to `active_character.json`.
  - Establish schema versioning (`schema_version: "2.0"`) and a lightweight migration dispatcher.
  - Provide minimal CLI subcommands (`sources`, `state`) using standard-library `argparse`.

- **No-Input Compliance Guard (Defense-in-Depth)**:
  - Implement static AST scanning (`companion/compliance/no_input_guard.py`) scoped to `companion/**/*.py` (excluding venvs, test fixtures, docs, data, runtime, and OpenSpec artifacts) to enforce the project's prohibited input/control dependencies and known API patterns at static-analysis time (rejecting direct, `from`, aliased imports, and calls to `pyautogui`, `pynput`, `keyboard`, `mouse`, `SendInput`, `keybd_event`, `mouse_event`).

## Capabilities

### New Capabilities
- `source-ingestion`: Unpack (with ZIP slip protection), validate, normalize, and manifest the nine expected pinned Fubgun build source snapshots while preserving raw immutability, passive weapon-set contexts, and interval shapes, with byte-for-byte deterministic canonical manifest output.
- `character-state`: Manage isolated, persistent per-character state with field-level provenance, semantic verification, cross-process single-writer locking (`msvcrt.locking`), crash-safe atomic writes, safe backup copy ordering, and bounded rolling backups.
- `no-input-compliance`: Statically inspect the companion codebase (`companion/**/*.py`) to enforce the project's prohibited input/control dependencies and known API patterns at static-analysis time.

### Modified Capabilities
*(None - greenfield project)*

## Impact

- **Code Structure**: Establishes `companion/sources/`, `companion/state/`, and `companion/compliance/` packages under Python 3.11+.
- **Dependencies**: Adds runtime dependencies on `pydantic` >= 2.0 and `PyYAML` >= 6.0; development dependencies on `pytest` and `pytest-cov`. Standard library `argparse` is used for CLI. Standard library `msvcrt` is used for Windows file locking.
- **Data & Storage**: Creates `data/source/` for immutable raw `.build` files, deterministic manifest, and rule skeleton; `data/reports/` for validation outputs; `runtime/` for local character JSON state and rolling backups. No database or external daemon required.
- **Security & Compliance**: Enforces the project's prohibited input/control dependencies and known API patterns at static-analysis time via defense-in-depth AST scanning.
