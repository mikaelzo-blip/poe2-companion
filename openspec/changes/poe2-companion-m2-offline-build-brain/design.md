# Design: M2 Offline Build Brain

## Context

M0 established immutable source ingestion, validated level intervals (`LevelInterval`), normalized weapon-set contexts (`WeaponSetContext`), and annotated meta-gem anomalies (`Cast on Dodge`) across the nine pinned Fubgun 0.5.5 snapshots. M1 established crash-safe persistent character state (`CharacterState v2`), provenance wrappers (`ProvenancedField`), and semantic verification states (`VerificationState`).

M2 introduces the deterministic, offline Build Brain that consumes these models to resolve progression phases, target variants, level eligibility, and structured deltas without live game sensors or execution engines.

See `proposal.md` for problem motivation and scope boundaries.

## Goals / Non-Goals

**Goals:**
- Provide a pure Python, deterministic domain package (`companion/build/`) operating offline.
- Define an explicit evaluator input contract (`BuildBrainInput`) accepting `CharacterState` and optional `selected_target_variant: TargetVariant | None = None`.
- Enforce strict boundary validation rejecting invalid character levels (level <= 0 or level > 100) via `InvalidCharacterLevelError`.
- Interpret normalized `level_interval` into four explicit states: `ACTIVE`, `FUTURE`, `EXPIRED`, `UNKNOWN`.
- Resolve character progression phase across 6 phases (`LEVELING_1_14`, `LEVELING_15_32`, `LEVELING_33_51`, `POST_52_53_68`, `LEVELING_69_84_FALLBACK`, `HIGH_END`) plus `UNKNOWN`.
- Deterministically bind `LEVELING_69_84_FALLBACK` (levels 69–84) to the `lvl 53-68` snapshot as an explicit companion fallback policy with recorded provenance (`COMPANION_FALLBACK_SOURCE_GAP`).
- Resolve high-end target variants (`LVL85`, `ENDGAME`, `MAGEBLOOD`, `DOT_CAP`) non-monotonically. When `progression_phase = HIGH_END` and `selected_target_variant is None`, return an explicit structured unresolved result (`TargetVariantResolution` with `variant: null`, `status: UNRESOLVED`, `reason: NO_EXPLICIT_HIGH_END_VARIANT`) without defaulting to `LVL85`. Outside high-end, return `variant: NONE` (`status: NOT_APPLICABLE`).
- Enforce that item possession (equipped or inventory) never silently selects or resolves target variants.
- Implement passive logical identity using compound key `(passive_id, weapon_set_context)` across all 4 weapon-set contexts, canonicalizing raw duplicate rows into single allocation requirements while preserving all raw `source_occurrences`, source row indices, and interval provenance. Surface material disagreements between duplicate occurrences as structured `CONFLICTING_EVIDENCE` records.
- Implement semantic skill-group identity deriving from primary/meta-gem identity, parent/meta context, and active child context, retaining source group index strictly for audit provenance. Reordering group indices across snapshots preserves identical logical interpretation. Distinguish standalone gems (e.g. standalone `Tornado`) from gems socketed inside meta-gem setups (e.g. `Tornado` inside `Cast on Dodge`), evaluate gem level eligibility (`Cast on Dodge` is `FUTURE` at level 52, never `MISSING`), and avoid inferring weapon-set assignments absent from `.build` files.
- Distinguish evidence quality from observation coverage via scoped `ObservationCoverage` (`COMPLETE`, `PARTIAL`, `UNKNOWN`). Enforce a centralized shared policy helper where `MISSING` requires an `ACTIVE` target, fresh observation, sufficient evidence quality, COMPLETE scoped coverage, and confirmed absence. Partial coverage evaluates to `UNKNOWN` with `reason: PARTIAL_PLAYER_OBSERVATION`.
- Implement conservative equipment delta comparing slot identifier, weapon-set context where applicable, unique name, base type, freshness, and slot-scoped coverage without gear scoring, upgrade scoring, affix optimization, pricing, economy logic, or OCR.
- Track target source availability (`USABLE`, `PENDING_VERIFICATION`, `UNAVAILABLE`) under Blueprint v2 precedence. Reserve the PoB2 precedence slot without implementing a PoB parser or fabricating unverified facts.
- Emit a comprehensive typed contract (`BuildDeltaResult`) for downstream consumption by M3 and M4.

**Non-Goals:**
- No persistent Level-52 transition state machine (`PREPARING`, `VERIFYING`, `BLOCKED`, `READY`, `TRANSITIONING`, `COMPLETE`, `MISSED_TRANSITION` belong strictly to M3).
- No rule evaluation engine or guide rule execution (belongs to M3).
- No target variant persistence, interactive prompting, or UI (selection is passed explicitly in `BuildBrainInput`; UX belongs outside M2).
- No objective ranking, candidate priority scoring, or tie-breaking (belongs to M4).
- No notifications, alerts, or human-facing advice prose (belongs to M4).
- No process monitoring, `Client.txt` tailing, or observation bus (belongs to M5).
- No screen capture, OCR, vision, tooltip parsing, or live memory reading.
- No item pricing, economy evaluation, trade searches, or automated gear scoring.
- No PoB parser (M2 consumes verified `.build` inputs and reserves the PoB2 precedence slot).
- No database, background daemon, event bus, or network services.

## Decisions

### 1. Modular, Decoupled Architecture under `companion/build/`

We structure M2 into small, single-responsibility modules under `companion/build/`:

```text
companion/build/
  __init__.py
  validation.py    # Boundary level validation & InvalidCharacterLevelError
  input.py         # BuildBrainInput contract
  eligibility.py   # LevelInterval -> EligibilityState evaluation
  progression.py   # CharacterState -> ProgressionPhase resolution (with 69-84 fallback)
  variants.py      # TargetVariant & TargetVariantResolution resolution
  passives.py      # Compound key identity, target canonicalization & duplicate conflict check
  skills.py        # Semantic skill-group identity, gem eligibility & delta
  equipment.py     # Conservative equipment slot delta
  conflicts.py     # Source precedence, source availability & CONFLICTING_EVIDENCE
  policy.py        # Shared UNKNOWN / STALE / MISSING delta policy helper with ObservationCoverage
  delta.py         # Root BuildDeltaResult contract & orchestrator
```

*Rationale*: This isolates domain rules into testable units, avoids monolithic evaluator files, keeps boundary test suites focused, and matches the personal-use simplicity guideline.

### 2. Explicit Evaluator Input Contract (`BuildBrainInput` & `PlayerObservationCoverage`)

`companion/build/input.py` defines:
```python
class ObservationCoverage(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"

class PlayerObservationCoverage(BaseModel):
    """Explicit observation coverage across character subsystems."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    passives: ObservationCoverage = ObservationCoverage.UNKNOWN
    skills: ObservationCoverage = ObservationCoverage.UNKNOWN
    equipment_slots: dict[str, ObservationCoverage] = Field(default_factory=dict)

class BuildBrainInput(BaseModel):
    """Explicit offline input contract for the M2 Build Brain."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    character_state: CharacterState
    observation_coverage: PlayerObservationCoverage = Field(default_factory=PlayerObservationCoverage)
    selected_target_variant: TargetVariant | None = None
```

*Rules*:
1. M2 Build Brain does not interactively prompt or maintain state persistence for `selected_target_variant` or `observation_coverage`.
2. The caller (test suite, CLI, or downstream M3/M4 coordinator) explicitly passes `character_state`, `observation_coverage`, and `selected_target_variant` in `BuildBrainInput`.
3. If `progression_phase == ProgressionPhase.HIGH_END` and `selected_target_variant is None`, the brain returns an explicit unresolved variant status.
4. `ObservationCoverage` remains strictly in the M2 Build Brain input/context layer; it is not retrofitted into the archived M0/M1 `CharacterState` schema. M3/M5 will populate this context from audits/sensors, while M2 only consumes it.

### 3. Explicit Eligibility States, Single-Uint Uncertainty & Invalid Level Validation

`companion/build/validation.py` defines:
```python
class InvalidCharacterLevelError(ValueError):
    """Raised when character level violates the supported range [1, 100]."""
    pass

def validate_character_level(level: int | None) -> int | None:
    """Validate character level against supported game bounds [1, 100].
    
    Returns None if level is None (unobserved).
    Raises InvalidCharacterLevelError if level <= 0 or level > 100.
    """
    if level is None:
        return None
    if not isinstance(level, int) or level <= 0 or level > 100:
        raise InvalidCharacterLevelError(
            f"Invalid character level: {level}. Level must be an integer between 1 and 100."
        )
    return level
```

`companion/build/eligibility.py` defines:
```python
class EligibilityState(str, Enum):
    ACTIVE = "ACTIVE"
    FUTURE = "FUTURE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"
```

Evaluation rules:
- `validate_character_level(level)` is executed at the boundary.
- `interval.is_unrestricted` -> `ACTIVE` (always, even if character level is unknown).
- `interval.is_range`:
  - character level is `None` or `UNKNOWN` -> `UNKNOWN`.
  - `level < min_level` -> `FUTURE`.
  - `min_level <= level <= max_level` -> `ACTIVE`.
  - `level > max_level` -> `EXPIRED`.
- `interval.is_unresolved` (single uint from M0):
  - Returns `UNKNOWN` with `unresolved_semantics=True`. Never fabricates `[X, 100]` or `[X, X]`.

*Rationale*: Preserves domain truth. In Path of Exile 2, level bounds determine when skills, gems, and items can be equipped. Invalid levels (0, negative, >100) are structural errors, not valid progression inputs; failing fast prevents silent downstream corruption.

### 4. Progression Phase Boundaries & Level 69–84 Fallback Policy

Progression phases map strictly to character level intervals:

| Progression Phase | Level Range | Default Target Snapshot | Decision Provenance |
|---|---|---|---|
| `LEVELING_1_14` | 1 – 14 | `lvl 1-14` | Canonical upstream snapshot |
| `LEVELING_15_32` | 15 – 32 | `lvl 15-32` | Canonical upstream snapshot |
| `LEVELING_33_51` | 33 – 51 | `lvl 33-51` | Canonical upstream snapshot |
| `POST_52_53_68` | 52 – 68 | `lvl 53-68` (or `lvl 52 Swap` transition baseline) | Canonical upstream snapshot |
| `LEVELING_69_84_FALLBACK` | 69 – 84 | `lvl 53-68` | `COMPANION_FALLBACK_SOURCE_GAP` (Fubgun guide lacks dedicated 69–84 snapshot) |
| `HIGH_END` | 85 – 100 | Resolved High-End Variant Snapshot | Explicit `selected_target_variant` input required |
| `UNKNOWN` | None / unobserved | None | Unobserved character level |

*Isolation Guard*: M2 progression resolution only identifies which stage applies. It explicitly checks that no M3 transition states (`PREPARING`, `VERIFYING`, `BLOCKED`, etc.) are computed or leaked into M2 outputs.

*Fallback Policy Provenance*: Levels 69–84 use `lvl 53-68` as deterministic fallback reference. This does not rename the snapshot or assert upstream author coverage through 84; it is a companion fallback policy resulting from the source gap between level 68 and level 85.

### 5. High-End Variants & Removal of Implicit LVL85 Default

Valid high-end target variants are:
- `LVL85` (`lvl 85` snapshot)
- `ENDGAME` (`Endgame` snapshot)
- `MAGEBLOOD` (`Mageblood` snapshot)
- `DOT_CAP` (`DoT Cap` snapshot)

Outside high-end (levels 1–84 or unknown level), target variant resolves to `NONE` with status `NOT_APPLICABLE`.

Inside `HIGH_END` (levels 85–100):
Variant resolution follows a structured model:
```python
class VariantResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"

class TargetVariantResolution(BaseModel):
    variant: TargetVariant | None = None
    status: VariantResolutionStatus
    reason: str | None = None
    source: str | None = None
```

Rules:
1. When `progression_phase == ProgressionPhase.HIGH_END` and `selected_target_variant is None`, the resolver returns:
   ```python
   TargetVariantResolution(
       variant=None,
       status=VariantResolutionStatus.UNRESOLVED,
       reason="NO_EXPLICIT_HIGH_END_VARIANT"
   )
   ```
   The resolver SHALL NOT default to `LVL85`. Doing so would violate the UNKNOWN-vs-assumption invariant.
2. When an explicit selection is provided (`LVL85`, `ENDGAME`, `MAGEBLOOD`, or `DOT_CAP`), the resolver returns `status=RESOLVED` with the selected variant.
3. Item ownership (possessing or equipping Mageblood) MUST NOT silently resolve or mutate the variant. Only an explicit input/persisted choice or future approved deterministic configuration establishes the variant.
4. Variants are independent and non-monotonic: `MAGEBLOOD` is not a superset of `ENDGAME`, and `DOT_CAP` is not a superset of `MAGEBLOOD`. Switching variants removes superseded requirements and adds new requirements.

### 6. Compound Passive Logical Identity, Hardened Canonicalization & Conflict Detection

Passive identity is:
```python
PassiveLogicalKey = tuple[str, WeaponSetContext]
```

Where `WeaponSetContext` is:
- `DEFAULT_OR_SHARED`
- `SPECIALISATION_1`
- `SPECIALISATION_2`
- `UNKNOWN_RESERVED`

*Hardened Canonicalization Strategy*:
A normalized build snapshot may contain raw duplicate passive rows (e.g. `dexterity30_` twice in `DEFAULT_OR_SHARED`). The target passive requirement model (`CanonicalTargetPassive`) canonicalizes raw rows into a single logical requirement while preserving all occurrence metadata:

```python
class CanonicalTargetPassive(BaseModel):
    key: tuple[str, WeaponSetContext]
    passive_id: str
    weapon_set_context: WeaponSetContext
    required_count: int = 1  # Exactly 1 allocation required
    source_occurrences: int  # Total raw rows (e.g. 2)
    source_indices: list[int]  # Raw row indices (e.g. [9, 21])
    raw_weapon_sets: list[int | None]
    has_conflict: bool = False
```

*Conflict Detection on Duplicate Occurrences*:
When multiple raw rows map to the same logical key:
- If raw occurrences are identical in relevant metadata (e.g. same level interval and attributes), they canonicalize cleanly into 1 requirement with `has_conflict = False`.
- If raw occurrences have materially conflicting semantics (e.g. differing level intervals, incompatible required conditions), the system sets `has_conflict = True` and generates a structured `ConflictRecord` under `conflicts`. The resolver does NOT silently discard or select one occurrence.

*Non-Monotonic Variant Re-evaluation*:
When the target variant changes (e.g. `MAGEBLOOD` -> `DOT_CAP`), passive requirements are recomputed from the new snapshot, adding new passive requirements (such as dual weapon-set specializations for `fire62`) and removing requirements unique to the prior variant.

### 7. Semantic Skill-Group Identity Model & Meta-Gem Representation

Skills are NOT flattened into a global set of gem IDs, and logical skill identity is NOT keyed to volatile source group indices.

*Logical Semantic Identity*:
```python
SkillGroupLogicalKey = tuple[str, str | None]  # (primary_gem_id, parent_meta_gem_id)
```

Skill groups are identified by their semantic structure:
- `primary_gem_id`: Identifies the active skill or meta-gem (e.g. `SkillGemTornado` or `SkillGemCastOnDodge`).
- `parent_meta_gem_id`: Identifies the parent meta-gem context if this gem is socketed inside a meta-gem trigger (`None` for standalone active skills).
- `active_child_context`: Captures child active skills triggered by the meta-gem.

The raw `source group_index` is preserved strictly for provenance/audit. If source group indices are reordered across build snapshots or exports while semantic groups remain identical, the system derives identical logical requirements and deltas.

*Real-Source Fixture*:
In `lvl 52 Swap - 0.5.5 Fubgun Flameblast Oi.build`:
- Standalone Tornado: Primary `SkillGemTornado`, parent `None`, interval `[41, 100]`, supports `Expand`, `AdvancingStorm`, `PersistenceTwo`.
- Cast on Dodge Setup: Primary `SkillGemCastOnDodge`, parent `None`, interval `[58, 100]`, socketed child gems: `SkillGemTornado`, `AdvancingStorm`, `MagnifiedEffectTwo`.

*Skill Group Data Models*:
```python
class TargetSupportGem(BaseModel):
    id: str
    level_interval: LevelInterval
    is_cast_on_dodge: bool = False
    source_provenance: str | None = None

class TargetSkillGroup(BaseModel):
    logical_key: tuple[str, str | None]
    primary_gem_id: str
    parent_meta_gem_id: str | None = None
    level_interval: LevelInterval
    is_meta_gem: bool = False
    support_skills: list[TargetSupportGem] = Field(default_factory=list)
    source_group_index: int  # Retained strictly for audit provenance
    source_provenance: str | None = None
```

Rules:
1. Supports belong strictly to their target skill group.
2. Semantic key `(primary_gem_id, parent_meta_gem_id)` distinguishes standalone `Tornado` from Cast-on-Dodge `Tornado` regardless of source group indices.
3. Level eligibility is evaluated per gem interval: at level 52, `Cast on Dodge` (`[58, 100]`) evaluates to `FUTURE`. It does NOT evaluate to `MISSING`.
4. No weapon-set assignments are inferred or fabricated for skill groups because raw `.build` files do not specify them.

### 8. Centralized Observation Coverage & Shared Delta Policy Helper

To prevent false absence assertions, M2 distinguishes evidence quality (verification state) from observation coverage (comprehensiveness within scope).

`companion/build/policy.py` defines:

```python
class ObservationCoverage(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"

class DeltaStatus(str, Enum):
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    EXTRA = "EXTRA"
    UNKNOWN = "UNKNOWN"
    FUTURE = "FUTURE"
    EXPIRED = "EXPIRED"

class DeltaReason(str, Enum):
    NONE = "NONE"
    STALE_PLAYER_STATE = "STALE_PLAYER_STATE"
    PARTIAL_PLAYER_OBSERVATION = "PARTIAL_PLAYER_OBSERVATION"
    OBSERVATION_COVERAGE_UNKNOWN = "OBSERVATION_COVERAGE_UNKNOWN"
    UNOBSERVED_SUBSYSTEM = "UNOBSERVED_SUBSYSTEM"
    INSUFFICIENT_EVIDENCE_RELIABILITY = "INSUFFICIENT_EVIDENCE_RELIABILITY"
    INELIGIBLE_LEVEL = "INELIGIBLE_LEVEL"

def evaluate_delta_item(
    target_eligibility: EligibilityState,
    player_observation_exists: bool,
    is_stale: bool,
    verification_state: VerificationState,
    observation_coverage: ObservationCoverage,
    is_entity_present: bool,
) -> tuple[DeltaStatus, DeltaReason]:
    """Shared deterministic delta evaluator across passives, skills, and equipment."""
    if target_eligibility == EligibilityState.FUTURE:
        return DeltaStatus.FUTURE, DeltaReason.INELIGIBLE_LEVEL
    if target_eligibility == EligibilityState.EXPIRED:
        return DeltaStatus.EXPIRED, DeltaReason.INELIGIBLE_LEVEL
    if target_eligibility == EligibilityState.UNKNOWN:
        return DeltaStatus.UNKNOWN, DeltaReason.INELIGIBLE_LEVEL

    # Target requirement is ACTIVE
    if not player_observation_exists:
        return DeltaStatus.UNKNOWN, DeltaReason.UNOBSERVED_SUBSYSTEM

    if is_stale or verification_state == VerificationState.STALE:
        return DeltaStatus.UNKNOWN, DeltaReason.STALE_PLAYER_STATE

    if verification_state in (VerificationState.UNKNOWN, VerificationState.CONFLICTING):
        return DeltaStatus.UNKNOWN, DeltaReason.INSUFFICIENT_EVIDENCE_RELIABILITY

    # Check scoped observation coverage
    if observation_coverage == ObservationCoverage.UNKNOWN:
        return DeltaStatus.UNKNOWN, DeltaReason.OBSERVATION_COVERAGE_UNKNOWN

    if observation_coverage == ObservationCoverage.PARTIAL:
        # If entity is observed present, presence is established
        if is_entity_present:
            return DeltaStatus.PRESENT, DeltaReason.NONE
        # Partial coverage cannot prove absence
        return DeltaStatus.UNKNOWN, DeltaReason.PARTIAL_PLAYER_OBSERVATION

    # Observation is COMPLETE, verified, and fresh
    if is_entity_present:
        return DeltaStatus.PRESENT, DeltaReason.NONE
    else:
        return DeltaStatus.MISSING, DeltaReason.NONE
```

*Required MISSING Invariant*:
A delta item evaluates to `MISSING` if and only if ALL five conditions hold:
1. Target requirement is `ACTIVE`,
2. Relevant player observation is fresh (not stale),
3. Evidence quality is sufficient for definitive comparison (`VERIFIED` or `CORROBORATED`),
4. Observation coverage for the relevant scope is `COMPLETE`, and
5. The target entity is actually absent from observed state.

*Scoped Coverage Rules*:
- **Passives**: Scoped to the tree/checkpoint observation. If an audit only inspected a branch or subtree (`PARTIAL`), unseen target nodes evaluate to `UNKNOWN` with reason `PARTIAL_PLAYER_OBSERVATION`. If coverage is `UNKNOWN`, unseen target nodes evaluate to `UNKNOWN` with reason `OBSERVATION_COVERAGE_UNKNOWN`.
- **Skills**: Scoped to skill bar/gem sockets. If an audit is partial, unseen target skills evaluate to `UNKNOWN` with reason `PARTIAL_PLAYER_OBSERVATION`. If coverage is `UNKNOWN`, unseen target skills evaluate to `UNKNOWN` with reason `OBSERVATION_COVERAGE_UNKNOWN`.
- **Equipment**: Scoped per equipment slot in `observation_coverage.equipment_slots`:
  - An absent slot entry in `equipment_slots` means `UNKNOWN` coverage for that slot.
  - A complete, fresh observation for a specific slot (e.g. helmet) can evaluate `MISSING` for that slot even if rings, body armour, or weapons are unobserved.
  - Coverage for helmet MUST NOT imply coverage for boots, body armour, or weapons.
  - Omitted or unobserved slots evaluate to `UNKNOWN` with reason `UNOBSERVED_SUBSYSTEM` (if unobserved in state) or `OBSERVATION_COVERAGE_UNKNOWN` (if observed but coverage unestablished).
- **Conservative Default & Non-Inference Rules**:
  - Coverage not supplied / not known defaults to `UNKNOWN`, guaranteeing that absence cannot become `MISSING`.
  - Coverage is NEVER inferred from `VerificationState.VERIFIED` alone (an observation being verified does not establish completeness).
  - Coverage is NEVER inferred from the number of observed entities, character level, or presence of other equipment slots.
  - Freshness and verification remain sourced from `CharacterState` and `ProvenancedField` metadata; observation coverage is an independent concern supplied explicitly in `BuildBrainInput`.
  - `ObservationCoverage` lives strictly in the M2 input/context layer, avoiding retrofitting archived M0/M1 `CharacterState` schemas.

### 9. Conservative Equipment Delta

Equipment delta compares factual observations using the existing `CharacterState` structure without speculative AI or external services:
```python
class EquipmentDeltaEntry(BaseModel):
    slot_id: str                      # e.g. "Weapon1", "Helm", "BodyArmour"
    weapon_set_context: str | None    # e.g. "Weapon1" vs "Weapon2" where applicable
    expected_unique_name: str | None
    observed_unique_name: str | None
    status: DeltaStatus               # PRESENT, MISSING, UNKNOWN, FUTURE
    reason: DeltaReason = DeltaReason.NONE
    observed_provenance: str | None = None
```

*Explicit Non-Goals*:
- No gear scoring, upgrade scoring, or affix optimizer.
- No item pricing, economy evaluation, or trade searches.
- No OCR or live inventory scraping.
- Unknown equipment observations remain `UNKNOWN`.

### 10. Source Precedence, Availability & Conflict Representation

Precedence follows Blueprint v2:
1. Explicit verified written Fubgun rule
2. Active stage `.build`
3. Adjacent `.build`
4. PoB2 high-end reference *(Precedence slot reserved; direct consumption NOT active in M2; no PoB parser)*
5. Labeled inference

Target Source Availability Tracking:
```python
class SourceAvailability(str, Enum):
    USABLE = "USABLE"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    UNAVAILABLE = "UNAVAILABLE"
```
The target resolver checks the project source registry before evaluating requirements. Unregistered or unintegrated sources (such as PoB2) evaluate to `UNAVAILABLE`. M2 does not fabricate PoB2 facts.

Conflict Representation:
```python
class ConflictRecord(BaseModel):
    field_name: str
    conflicting_sources: list[str]
    conflicting_values: list[Any]
    status: str = "CONFLICTING_EVIDENCE"
```
Unresolvable equal-precedence disagreements produce a `ConflictRecord` in `BuildDeltaResult.conflicts`.

### 11. Root M2 Output Contract (`BuildDeltaResult`)

```python
class BuildDeltaResult(BaseModel):
    character_id: str
    character_level: int | None
    progression_phase: ProgressionPhase
    target_variant_resolution: TargetVariantResolution
    target_stage_name: str | None
    target_manifest_sha256: str | None
    
    passives: list[PassiveDeltaEntry]      # PRESENT, MISSING, EXTRA, UNKNOWN
    skills: list[SkillGroupDeltaEntry]     # PRESENT, MISSING, UNKNOWN, FUTURE
    equipment: list[EquipmentDeltaEntry]  # PRESENT, MISSING, UNKNOWN, FUTURE
    
    conflicts: list[ConflictRecord]
    unknowns: list[str]
    is_fully_audited: bool
```

Downstream components (M3 transition watcher, M4 objective generator) consume this model directly.

## Risks / Trade-offs

- **[Risk] Levels 69–84 have no dedicated Fubgun snapshot**: Fubgun's guide jumps from `lvl 53-68` to `lvl 85`.
  *Mitigation*: Phase `LEVELING_69_84_FALLBACK` maps deterministically to `lvl 53-68` as fallback reference and records provenance `COMPANION_FALLBACK_SOURCE_GAP`.
- **[Risk] High-end variant ambiguity**: If no variant is selected, downstream engines might fail if expecting a default.
  *Mitigation*: Returning an explicit `TargetVariantResolution` with `status: UNRESOLVED` forces downstream M3/M4 or UI to request or await an explicit variant choice, adhering strictly to UNKNOWN-vs-assumption principles.
- **[Risk] Passive string ID vs official PoE2 API hash**: Raw `.build` files use planner string IDs (`dexterity30_`, `fire62`).
  *Mitigation*: M2 compares facts using the normalized string IDs and compound keys `(passive_id, weapon_set_context)`.
- **[Risk] Downstream coupling**: Temptation to add transition readiness flags (`is_ready_for_swap`) or priority tags (`CRITICAL_MISSING`).
  *Mitigation*: Hard architectural boundary: M2 calculates factual differences (`PRESENT`, `MISSING`, `EXTRA`, `UNKNOWN`, `FUTURE`). Transition state machines belong to M3; priority weights belong to M4.

## Migration Plan

Not applicable. M2 is an additive domain package within `companion/build/`. It consumes existing M0 and M1 schemas without modifying database or state storage schemas.

## Open Questions

- *Single-uint level interval semantics*: Remains unresolved in M0/M1 data. M2 preserves this uncertainty as `UNKNOWN` with `unresolved_semantics=True` rather than inventing semantics. This is safe and non-blocking.
- *Downstream explicit high-end variant prompts*: M3/M4 will prompt the user when `TargetVariantResolution.status == UNRESOLVED` during character progression into high-end.
