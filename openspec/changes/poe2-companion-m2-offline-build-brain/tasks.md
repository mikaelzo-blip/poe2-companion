# Tasks

## 1. Boundary Level Defense, Eligibility Engine, and Property Tests

- [ ] 1.1 Implement boundary level validation `validate_character_level` and `InvalidCharacterLevelError` in `companion/build/validation.py`, strictly validating character levels in the supported range `[1, 100]` and rejecting invalid levels (level <= 0 or level > 100) at domain boundaries rather than silently mapping to progression phases.
- [ ] 1.2 Implement `EligibilityState` enum (`ACTIVE`, `FUTURE`, `EXPIRED`, `UNKNOWN`) and interval evaluator `evaluate_eligibility` in `companion/build/eligibility.py`, supporting unrestricted intervals, explicit closed ranges `[min, max]`, unknown character level defense, defensive rejection of inverted/malformed intervals, and preservation of single unsigned integer intervals as `UNKNOWN` with unresolved semantics flags without inventing custom bounds.
- [ ] 1.3 Implement property and boundary unit tests in `tests/build/test_eligibility.py` covering invalid level rejection (level 0, negative level -5, level 101+ raising `InvalidCharacterLevelError`), interval boundaries (`min - 1`, `min`, inside range, `max`, `max + 1`), unknown character levels, unrestricted intervals, unresolved single uint intervals, and defensive validation errors, verified by running `pytest tests/build/test_eligibility.py`.

## 2. Progression Phase, 69–84 Fallback, and Target Variant Resolvers

- [ ] 2.1 Implement `ProgressionPhase` enum (`LEVELING_1_14`, `LEVELING_15_32`, `LEVELING_33_51`, `POST_52_53_68`, `LEVELING_69_84_FALLBACK`, `HIGH_END`, `UNKNOWN`) and `resolve_progression_phase` in `companion/build/progression.py`, mapping level boundaries deterministically, explicitly binding `LEVELING_69_84_FALLBACK` (levels 69–84) to the `lvl 53-68` snapshot as a deterministic companion fallback policy with recorded provenance (`COMPANION_FALLBACK_SOURCE_GAP`), while strictly isolating from Milestone 3 transition state machine logic (`PREPARING`, `VERIFYING`, `BLOCKED`, `READY`, `TRANSITIONING`, `COMPLETE`, `MISSED_TRANSITION`).
- [ ] 2.2 Implement explicit input contract `BuildBrainInput` in `companion/build/input.py` (`character_state`, `observation_coverage: PlayerObservationCoverage = Field(default_factory=PlayerObservationCoverage)`, `selected_target_variant: TargetVariant | None = None`), `PlayerObservationCoverage` model (`passives`, `skills`, `equipment_slots: dict[str, ObservationCoverage]`), `TargetVariant` enum (`NONE`, `LVL85`, `ENDGAME`, `MAGEBLOOD`, `DOT_CAP`), structured `TargetVariantResolution` model (`variant`, `status`, `reason`, `source`), non-monotonic variant resolver `resolve_target_variant`, and target snapshot selector in `companion/build/variants.py`. Enforce that `NONE` applies outside `HIGH_END`, return `status=UNRESOLVED` with `reason=NO_EXPLICIT_HIGH_END_VARIANT` when in `HIGH_END` and `selected_target_variant is None` (never defaulting to `LVL85`), and prevent observed inventory or equipped items from silently mutating or resolving target variants.
- [ ] 2.3 Implement unit tests in `tests/build/test_progression_and_variants.py` verifying exact boundary transitions (levels 1, 14, 15, 32, 33, 51, 52, 53, 58, 68, 69, 84, 85, 100), snapshot transitions across 68 -> 69 -> 84 -> 85, unknown character level handling, high-end resolution with `selected_target_variant=None` returning `UNRESOLVED` (never defaulting to `LVL85`), explicit resolution of `LVL85`, `ENDGAME`, `MAGEBLOOD`, and `DOT_CAP`, non-monotonic variant independence, and refusal to auto-switch variants based on item ownership, verified by running `pytest tests/build/test_progression_and_variants.py`.

## 3. Passive Logical Identity, Hardened Canonicalization, and Passive Delta

- [ ] 3.1 Implement compound logical key `(passive_id, weapon_set_context)`, canonical target passive model (`CanonicalTargetPassive`) preserving all raw `source_occurrences`, original source row indices, and interval/provenance in `companion/build/passives.py`. Implement duplicate occurrence conflict inspection: identical duplicate rows canonicalize cleanly into 1 allocation requirement, while duplicate occurrences with materially conflicting metadata generate structured `ConflictRecord` entries with status `CONFLICTING_EVIDENCE`.
- [ ] 3.2 Implement passive delta evaluator in `companion/build/passives.py` supporting statuses `PRESENT`, `MISSING`, `EXTRA`, `UNKNOWN`, respecting non-monotonic target variant changes (adding and removing passive requirements) and scoped tree observation coverage.
- [ ] 3.3 Implement unit tests in `tests/build/test_passives.py` verifying:
  1. Identical duplicate raw rows canonicalize cleanly to 1 logical allocation requirement,
  2. Same passive ID with distinct weapon-set contexts (`DEFAULT_OR_SHARED`, `SPECIALISATION_1`, `SPECIALISATION_2`, `UNKNOWN_RESERVED`) produce separate compound keys and requirements,
  3. Duplicate logical keys with conflicting metadata produce structured `CONFLICTING_EVIDENCE` records,
  4. Target variant changes remove and add passive requirements,
  5. VERIFIED passive state with coverage UNKNOWN evaluates to `UNKNOWN` with reason `OBSERVATION_COVERAGE_UNKNOWN` and never `MISSING`,
  6. Fresh VERIFIED but PARTIAL passive observation evaluates to `UNKNOWN` with reason `PARTIAL_PLAYER_OBSERVATION` and never `MISSING`,
  7. Complete fresh passive observation with target absent evaluates to `MISSING`,
  8. Coverage is never inferred from `VerificationState.VERIFIED` alone, and
  9. Stale player observations evaluate to `UNKNOWN` with reason `STALE_PLAYER_STATE`, verified by running `pytest tests/build/test_passives.py`.

## 4. Semantic Skill-Group Identity, Scoped Observation Policy, and Delta Contracts

- [ ] 4.1 Implement semantic skill-group representation (`TargetSkillGroup`, `TargetSupportGem`) and skill group delta evaluation in `companion/build/skills.py` deriving logical identity from semantic structure (primary active/meta-gem identity, parent/meta context, and active child context) while retaining `source_group_index` strictly for audit provenance. Distinguish standalone active gems from child setups (e.g. standalone `Tornado` vs `Tornado` socketed inside `Cast on Dodge` in level 52 snapshot), evaluate gem level eligibility (`Cast on Dodge [58, 100]` is `FUTURE` at level 52, never `MISSING`), enforce semantic invariance under source group index reordering, and avoid inferring weapon-set assignments absent from `.build` files.
- [ ] 4.2 Implement conservative equipment delta in `companion/build/equipment.py` comparing slot identifier, weapon-set context where applicable, unique name, base type, freshness, and slot-scoped observation coverage without gear scoring, upgrade scoring, pricing, economy logic, or OCR.
- [ ] 4.3 Implement source availability tracking (`USABLE`, `PENDING_VERIFICATION`, `UNAVAILABLE`) and conflict structures in `companion/build/conflicts.py` (`CONFLICTING_EVIDENCE`), reserving the Blueprint v2 PoB2 precedence slot for future integration without fabricating PoB2 facts or introducing a PoB parser.
- [ ] 4.4 Implement `ObservationCoverage` enum (`COMPLETE`, `PARTIAL`, `UNKNOWN`), shared delta evaluation policy helper `evaluate_delta_item` in `companion/build/policy.py`, and root `BuildDeltaResult` orchestrator in `companion/build/delta.py`. Strictly enforce that `MISSING` is only returned when an active requirement is absent from fresh, verified observations with `COMPLETE` scoped coverage; partial coverage evaluates to `UNKNOWN` with reason `PARTIAL_PLAYER_OBSERVATION`; unestablished coverage evaluates to `UNKNOWN` with reason `OBSERVATION_COVERAGE_UNKNOWN`; stale player observations evaluate to `UNKNOWN` with reason `STALE_PLAYER_STATE`; unobserved state evaluates to `UNKNOWN` with reason `UNOBSERVED_SUBSYSTEM`.
- [ ] 4.5 Implement unit tests in `tests/build/test_skills_equipment_delta.py` verifying real-source level 52 fixture distinction between standalone `Tornado` and Cast-on-Dodge `Tornado`, semantic skill group invariance under index reordering, `Cast on Dodge` future status at level 52, skill coverage behavior (partial skill audit producing `UNKNOWN` with `PARTIAL_PLAYER_OBSERVATION`, complete skill audit producing `MISSING` for confirmed absent active skill, unsupplied/unknown coverage producing `UNKNOWN`), equipment slot missing from `equipment_slots` map evaluating to `UNKNOWN`, slot-scoped complete equipment observation establishing `MISSING` for that slot, and proving coverage for helmet does not imply coverage for boots or weapons, verified by running `pytest tests/build/test_skills_equipment_delta.py`.

## 5. Golden Scenarios, Invariants, and Full Suite Verification

- [ ] 5.1 Implement comprehensive golden scenario test suite in `tests/build/test_golden_scenarios.py` exercising end-to-end evaluation against real M0 normalized Fubgun snapshots across levels (1, 14, 15, 32, 33, 51, 52, 53, 58, 68, 69, 84, 85), snapshot transitions (proving 68 -> `POST_52_53_68`, 69 -> `LEVELING_69_84_FALLBACK` using `lvl 53-68` with provenance, 84 -> `LEVELING_69_84_FALLBACK`, 85 -> `HIGH_END`), high-end variants (`LVL85`, `ENDGAME`, `MAGEBLOOD`, `DOT_CAP`), unobserved player states, partial audits, stale observations, and conflicting target evidence.
- [ ] 5.2 Implement invariant property tests in `tests/build/test_invariants.py` explicitly proving the core domain invariants:
  1. VERIFIED passive state with coverage UNKNOWN evaluates to `UNKNOWN` (`OBSERVATION_COVERAGE_UNKNOWN`), never `MISSING`,
  2. Fresh VERIFIED but PARTIAL passive observation evaluates to `UNKNOWN` (`PARTIAL_PLAYER_OBSERVATION`), never `MISSING`,
  3. Complete fresh passive observation with target absent evaluates to `MISSING`,
  4. Skill coverage behaves equivalently (UNKNOWN coverage -> `UNKNOWN`, PARTIAL -> `PARTIAL_PLAYER_OBSERVATION`, COMPLETE -> `MISSING` when absent),
  5. Equipment slot missing from `equipment_slots` coverage map evaluates to `UNKNOWN` (`OBSERVATION_COVERAGE_UNKNOWN`),
  6. One equipment slot COMPLETE establishes absence (`MISSING`) for that slot only,
  7. Coverage for helmet must not imply coverage for boots or weapons,
  8. Coverage must never be inferred from `VerificationState.VERIFIED`,
  9. Source skill group indices reordered while semantic groups remain identical produces unchanged logical interpretation,
  10. `HIGH_END` with `selected_target_variant=None` returns `TargetVariantResolution(status=UNRESOLVED, reason=NO_EXPLICIT_HIGH_END_VARIANT)`, never silently defaulting to `LVL85`,
  11. 69–84 fallback is deterministic (binds to `lvl 53-68` with fallback provenance),
  12. Duplicate raw passive rows do not create duplicate allocation requirements,
  13. Conflicting duplicate passive metadata produces structured `CONFLICTING_EVIDENCE`,
  14. Distinct weapon-set contexts produce separate passive logical identities,
  15. Standalone `Tornado` and `Cast on Dodge -> Tornado` remain distinct skill requirements,
  16. `Cast on Dodge` at level 52 evaluates to `FUTURE`, never `MISSING`,
  17. Stale or unobserved player data evaluates to `UNKNOWN` with reason, never `MISSING`,
  18. Invalid character levels (<= 0 or > 100) are rejected with `InvalidCharacterLevelError`,
  19. Determinism: identical inputs produce identical `BuildDeltaResult`,
  20. Changing high-end target variant adds and removes requirements non-monotonically.
- [ ] 5.3 Verify the complete test and compliance suite passes: run `pytest tests/compliance/test_no_input_guard.py tests/build/`.
