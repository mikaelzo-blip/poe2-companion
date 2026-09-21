# Spec Delta

## Purpose

Provides immutable ingestion, deterministic verification, shape validation, ZIP slip protection, and anomaly reporting for the nine expected pinned Fubgun 0.5.5 build snapshots from the supplied source archive.

## ADDED Requirements

### Requirement: Immutable Raw Source Extraction with ZIP Slip Protection
The system SHALL extract all nine expected pinned Fubgun 0.5.5 `.build` snapshot files from the supplied source archive into an immutable source directory without mutating original file bytes or metadata. The extraction procedure SHALL validate every archive member prior to writing, rejecting path-traversal sequences (`../`), absolute paths, Windows drive-qualified paths, and any resolved output path escaping the target extraction directory. Only the expected `.build` source files may be materialized into the immutable raw-source directory.

#### Scenario: Successful extraction of all nine pinned snapshots
- **WHEN** the source unpacker is invoked with a valid archive path containing the nine expected pinned snapshots
- **THEN** exactly nine `.build` files corresponding to the known progression stages are extracted to the target directory and match their expected byte lengths

#### Scenario: Malicious or traversing archive entry rejected (ZIP slip protection)
- **WHEN** the source unpacker encounters an archive member with `../` path traversal, an absolute path, a drive-qualified path, or a path escaping the intended extraction root
- **THEN** extraction is aborted immediately with a path traversal validation error before any file is written

#### Scenario: Archive tampering or missing snapshot detection
- **WHEN** the source unpacker is invoked with an archive missing one or more required snapshot files or containing unexpected files
- **THEN** the system fails validation and records the missing or extraneous files in an error report

### Requirement: Separation of Raw and Normalized Build Data
The system SHALL maintain strict separation between raw build representations (`RawBuild*`) and normalized build representations (`NormalizedBuild*`), preserving unknown attributes and raw source occurrences without data loss.

#### Scenario: Raw build retains unmodeled properties
- **WHEN** a `.build` file containing undocumented or unmodeled JSON fields is parsed into a raw model
- **THEN** all extra fields are retained in the raw model rather than being discarded or causing validation failure

#### Scenario: Normalized build produces typed views while raw data remains intact
- **WHEN** a raw build model is transformed into a normalized build model
- **THEN** normalized typed accessors are generated while the raw source representation remains immutable

### Requirement: Conservative Level Interval Validation
The system SHALL validate `level_interval` attributes into explicit two-element unsigned integer ranges `[min, max]`, absent/unrestricted values, or single unsigned integers. The system SHALL reject invalid shapes, negative values, and descending ranges (`min > max`). For single unsigned integers, the system SHALL preserve the value as a valid source shape while recording its evaluation semantics as unresolved/unsupported without inventing custom behavior.

#### Scenario: Valid two-element interval parsing
- **WHEN** a `level_interval` attribute is a list of two non-negative integers `[min, max]` where `min <= max`
- **THEN** the system validates the interval as an explicit range with lower bound `min` and upper bound `max`

#### Scenario: Omitted interval defaults to unrestricted
- **WHEN** a `level_interval` attribute is `None` or omitted
- **THEN** the system treats the interval as unrestricted across all levels

#### Scenario: Single unsigned integer preserved as unresolved shape
- **WHEN** a `level_interval` attribute is a single non-negative integer
- **THEN** the system validates the shape, preserves the integer value, and marks the semantic interpretation as unresolved and unsupported

#### Scenario: Invalid negative or inverted bounds rejected
- **WHEN** a `level_interval` attribute contains negative numbers, more or fewer than two elements (when not a single integer), or `min > max`
- **THEN** the system rejects the interval with a source validation error

### Requirement: Passive Identity Preservation with Weapon-Set Context
The system SHALL identify passive entries by the compound logical key `(passive_id, weapon_set_context)` and SHALL NOT deduplicate passive entries using `passive_id` alone.

#### Scenario: Identical passive ID in multiple weapon-set contexts preserved
- **WHEN** a snapshot contains the same `passive_id` under different weapon-set contexts (such as Specialisation 1 and Specialisation 2)
- **THEN** the system preserves each occurrence as a distinct logical entry and retains occurrence counts for audit

#### Scenario: Weapon-set context values mapped conservatively
- **WHEN** an entry specifies `weapon_set` as omitted, `1`, `2`, or `0`
- **THEN** the system normalizes omitted to `DEFAULT_OR_SHARED`, `1` to `SPECIALISATION_1`, `2` to `SPECIALISATION_2`, and `0` to `UNKNOWN_RESERVED` without inferring unverified semantics

### Requirement: Meta-Gem and Source Anomaly Annotation
The system SHALL inspect build skills and supports for known source anomalies—specifically the `Cast on Dodge` meta-gem—and annotate them in validation reports without altering the underlying build definitions.

#### Scenario: Cast on Dodge detected and annotated
- **WHEN** a build snapshot contains `Cast on Dodge` with a level interval beginning at level 58
- **THEN** the system flags the entry as a known meta-gem source anomaly noting lack of official planner support, without removing it from the build

#### Scenario: Unknown source fields surfaced as warnings
- **WHEN** unmodeled fields or unexpected markup are encountered during parsing
- **THEN** the system emits validation warnings and logs them to the anomaly report

### Requirement: Deterministic Canonical Manifest and Anomaly Report Generation
The system SHALL compute SHA-256 hashes and byte counts for all raw build sources and generate a canonical `data/source/manifest.json`. The canonical manifest SHALL NOT include wall-clock or run timestamps (such as `extracted_at`) and SHALL enforce deterministic key ordering and serialization such that identical source archive bytes and tool version produce byte-for-byte identical canonical manifest output. Operational execution timestamps SHALL be recorded exclusively in anomaly report metadata.

#### Scenario: Deterministic manifest generation
- **WHEN** the manifest generator is executed against the extracted build snapshots across multiple runs with identical source bytes
- **THEN** it outputs `manifest.json` with identical SHA-256 hashes, file sizes, and stage names, producing byte-for-byte identical output without run timestamps

#### Scenario: Source anomaly report outputs with operational metadata
- **WHEN** source validation completes
- **THEN** machine-readable JSON and human-readable Markdown anomaly reports are generated documenting all warnings, anomalies, validation statuses, and operational run timestamps

### Requirement: Guide Rules Schema and Source Integrity
The system SHALL provide an initial schema and skeleton for `data/source/guide_rules.yaml`. Because the authoritative written Fubgun guide source is not yet frozen in the repository, the system SHALL NOT invent or encode unverified Fubgun rules. Any rule derived strictly from Blueprint v2 SHALL explicitly declare its provenance as `BLUEPRINT_V2`. Any rule requiring external written guide verification SHALL remain marked `PENDING_SOURCE_VERIFICATION`. No executable rule engine is permitted in M0 or M1.

#### Scenario: Guide rules structure declares provenance
- **WHEN** `guide_rules.yaml` is validated
- **THEN** every defined rule includes explicit provenance metadata, items requiring unverified external guide text are marked `PENDING_SOURCE_VERIFICATION`, and no executable logic is invoked
