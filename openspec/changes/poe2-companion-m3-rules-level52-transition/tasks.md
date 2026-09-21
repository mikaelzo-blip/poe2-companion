# Tasks

## 1. Rule Schema, Metadata Models, and Source Loader

- [ ] 1.1 Implement declarative rule enums (`RuleSourceType`, `SourceVerificationStatus`, `ObservabilityMethod`, `RuleEvaluationState`, `RequirementType`, and explicit `TransitionRuleRole`: `BLOCKING_REQUIREMENT`, `COMPLETION_EVIDENCE`, `ADVISORY`, `PREPARATION`) and `GuideRule` Pydantic model in `companion/rules/schema.py`, ensuring `transition_role` is explicitly modeled and decoupled from `RequirementType`, observability methods, or rule provenance. Verify with unit tests in `tests/rules/test_schema.py`.
- [ ] 1.2 Implement YAML guide rule loader `load_guide_rules` in `companion/rules/loader.py` to parse declarative rules from `data/source/guide_rules.yaml` into validated `GuideRule` instances, parsing and validating explicit `transition_role` and marking rules without supported observation paths as `evaluable=False`. Verify with unit tests in `tests/rules/test_loader.py`.
- [ ] 1.3 Implement unit tests in `tests/rules/test_schema.py` and `tests/rules/test_loader.py` verifying rule schema validation, strict enum enforcement, loading of the frozen `guide_rules.yaml` fixture, decoupling of transition roles from requirement types, and proper handling of inevaluable rules, verified by running `pytest tests/rules/`.

## 2. Semantic Rule Evaluator and Source Verification Gating

- [ ] 2.1 Implement `RuleEvaluationResult` model and stateless evaluator `evaluate_rule` in `companion/rules/evaluator.py`, mapping evaluations to six explicit states (`PASS`, `FAIL`, `UNKNOWN`, `NOT_APPLICABLE`, `STALE`, `CONFLICTING_EVIDENCE`), strictly enforcing that unobserved evidence produces `UNKNOWN` and stale evidence produces `STALE`, never converting to `FAIL`.
- [ ] 2.2 Implement source trust gating in `companion/rules/evaluator.py`: when a rule's source verification status is `PENDING_SOURCE_VERIFICATION` (or `UNAVAILABLE`), clamp its evaluation to `UNKNOWN` with reason `PENDING_SOURCE_VERIFICATION`, preventing unverified external guide rules from producing `PASS` or `FAIL`, from independently causing `BLOCKED`, from independently proving `COMPLETE`, and from being counted as an unsatisfied authoritative blocker that deadlocks `READY`.
- [ ] 2.3 Implement unit tests in `tests/rules/test_evaluator.py` verifying six-state evaluation, absence of evidence producing `UNKNOWN`, stale observation producing `STALE`, contradictory evidence producing `CONFLICTING_EVIDENCE`, and source verification gating preventing `PENDING_SOURCE_VERIFICATION` rules from asserting blockers or deadlocking `READY`, verified by running `pytest tests/rules/test_evaluator.py`.

## 3. Tri-State Requirement Evaluation and Future Requirement Isolation

- [ ] 3.1 Implement `RequirementReadiness` enum (`SATISFIED`, `UNSATISFIED`, `UNKNOWN`) and `RequirementEvaluation` model in `companion/transition/requirements.py`, implementing requirement aggregators that consume M2 `BuildDeltaResult` (equipment delta, skill delta, passive delta) and M1 character state, enforcing that only `USABLE` rules with role `BLOCKING_REQUIREMENT` gate transition blocking or readiness.
- [ ] 3.2 Implement future requirement isolation in `companion/transition/requirements.py`: consume M2 `EligibilityState`, strictly excluding requirements with progression state `FUTURE` (such as Cast on Dodge with interval `[58, 100]` at level 52) from the level-52 blocking requirements set so they never block transition readiness.
- [ ] 3.3 Implement unit tests in `tests/transition/test_requirements.py` verifying tri-state requirement evaluations (`SATISFIED`, `UNSATISFIED`, `UNKNOWN`), proving `UNKNOWN` is neither satisfied nor an active blocker, verifying M2 delta consumption, and verifying Cast on Dodge at level 52 evaluates as `FUTURE` and non-blocking, verified by running `pytest tests/transition/test_requirements.py`.

## 4. Level-52 Persistent Transition State Machine and Status Flags

- [ ] 4.1 Implement `Level52TransitionState` enum (`NOT_RELEVANT`, `PREPARING`, `VERIFYING`, `BLOCKED`, `READY`, `TRANSITIONING`, `COMPLETE`), root `Level52TransitionResult` model, and derived current-condition status properties `transition_pending` and `missed_transition` in `companion/transition/state.py`.
- [ ] 4.2 Implement deterministic transition evaluator `evaluate_level52_transition` and transition trigger `trigger_transition_start` in `companion/transition/evaluator.py`, enforcing:
  1. `level < 52`: evaluates to `NOT_RELEVANT` unless an applicable `USABLE` rule with role `PREPARATION` is satisfied (which sets `PREPARING`); no invented preparation thresholds (45/50/51); `PENDING_SOURCE_VERIFICATION` rules cannot establish `PREPARING`,
  2. `level >= 52` with unobserved/stale evidence or pending verification: `VERIFYING` (never `BLOCKED` from uncertainty),
  3. `level >= 52` with verified failed `USABLE` `BLOCKING_REQUIREMENT`: `BLOCKED`,
  4. `level >= 52` with all applicable `USABLE` blockers satisfied: `READY` (pending rules do not deadlock `READY`),
  5. `READY -> TRANSITIONING` requires explicit trigger event,
  6. `TRANSITIONING -> COMPLETE` requires verified post-swap evidence matching `USABLE` `COMPLETION_EVIDENCE` rules; does not require exact equality to the full lvl52 snapshot; does not infer skill weapon-set assignments from `.build`,
  7. `transition_pending` is deterministically derived as `level > 52 and state != COMPLETE`,
  8. `missed_transition` is deterministically derived as `level > 52 and state != COMPLETE and verified pre-swap evidence active`, resolving to `False` once `COMPLETE`,
  9. Late install at level >= 52 with verified completion evidence: directly resolves `COMPLETE` without `missed_transition`; insufficient evidence resolves to `VERIFYING`,
  10. Idempotent `COMPLETE`: level advancement to 58+ preserves `COMPLETE`.
- [ ] 4.3 Implement unit tests in `tests/transition/test_state_machine.py` verifying all valid state transitions, invalid transition rejections, `BLOCKED` vs `VERIFYING` distinction, `READY` requirements, late-install direct completion at level 60, `missed_transition` derivation on verified pre-swap build, and explicit transition start signal, verified by running `pytest tests/transition/test_state_machine.py`.

## 5. Schema 3.0 Persistence, Migration, and Round-Trip Safety

- [ ] 5.1 Implement `Level52TransitionRecord` model and update `CharacterState` in `companion/state/schema.py` to schema version `3.0`, adding the persistent field `transition: Level52TransitionRecord | None = None`.
- [ ] 5.2 Implement `migrate_2_0_to_3_0` in `companion/state/migrations.py` and register it in `MIGRATION_REGISTRY`, setting `transition = None` (uninitialized) without inferring historical transition state during schema migration. Implement deterministic initialization on first post-migration evaluation.
- [ ] 5.3 Implement unit tests in `tests/state/test_schema_v3_migration.py` verifying sequential migration from `1.0` -> `2.0` -> `3.0`, direct migration from `2.0` -> `3.0` leaving `transition = None` for levels 20, 52, and 60, followed by deterministic initialization on first evaluation, round-trip persistence of transition state across process restart, and rejection of unrecognized future schema versions (e.g. `4.0`), verified by running `pytest tests/state/test_schema_v3_migration.py`.

## 6. Golden Scenarios, Invariant Property Tests, and Suite Verification

- [ ] 6.1 Implement comprehensive golden scenario test suite in `tests/transition/test_golden_scenarios.py` exercising:
  1. Level 51 pre-transition without usable preparation rule (`NOT_RELEVANT`),
  2. Level 51 with usable `PREPARATION` rule satisfied/applicable (`PREPARING`),
  3. `PENDING_SOURCE_VERIFICATION` preparation rule does not trigger `PREPARING` authoritatively (`NOT_RELEVANT`),
  4. `PENDING_SOURCE_VERIFICATION` blocking rule cannot create `BLOCKED`,
  5. `PENDING_SOURCE_VERIFICATION` rule does not permanently deadlock or prevent `READY` when all usable blockers pass,
  6. Level 52 with no observations (`VERIFYING`),
  7. Level 52 with partial observations (`VERIFYING`),
  8. Level 52 with stale observations (`VERIFYING`),
  9. Level 52 with one verified failed usable blocker (`BLOCKED`),
  10. Level 52 with all currently applicable usable blockers satisfied (`READY`),
  11. Level 52 with Cast on Dodge `FUTURE` (evaluates `READY`),
  12. Level 53 incomplete (`transition_pending = True`, `VERIFYING` or `BLOCKED`),
  13. Level 58 advancement where Cast on Dodge becomes `ACTIVE` (level-52 transition remains `COMPLETE`),
  14. Level 60 late install with exact historical post-swap evidence (`COMPLETE`, `missed_transition = False`),
  15. Level 60 evolved build with sufficient completion markers (`COMPLETE`, `missed_transition = False`),
  16. Level 60 with verified pre-swap build (`BLOCKED`, `missed_transition = True`),
  17. Level 60 current build differs from lvl52 snapshot and evidence insufficient (`VERIFYING`, `transition_pending = True`, `missed_transition = False`),
  18. Skill weapon-set inference is not used for completion,
  19. Migrated 2.0 state at level 20 has `transition = None`, first evaluation initializes to `NOT_RELEVANT`,
  20. Migrated 2.0 state at level 52 has `transition = None`, first evaluation initializes to `VERIFYING`,
  21. Migrated 2.0 state at level 60 with completion evidence has `transition = None`, first evaluation initializes to `COMPLETE`,
  22. Restart while `VERIFYING` preserves state,
  23. Restart while `BLOCKED` preserves state,
  24. Restart while `READY` preserves state,
  25. Restart while `COMPLETE` preserves state,
  26. Conflicting source/evidence yields `CONFLICTING_EVIDENCE`.
- [ ] 6.2 Implement invariant property tests in `tests/transition/test_invariants.py` proving:
  1. No invented pre-52 preparation threshold (level < 52 is `NOT_RELEVANT` unless explicit usable preparation rule exists),
  2. Requirement type does not implicitly determine transition role,
  3. Only `USABLE` `BLOCKING_REQUIREMENT` rules can directly cause `BLOCKED`,
  4. `PENDING_SOURCE_VERIFICATION` rules cannot deadlock `READY`,
  5. Only `USABLE` `COMPLETION_EVIDENCE` may prove `COMPLETE`,
  6. `COMPLETE` does not require exact equality to lvl52 snapshot,
  7. No skill weapon-set inference is required for `COMPLETE`,
  8. Schema migration does not invent historical transition state (`transition = None`),
  9. First post-migration evaluation is deterministic,
  10. `transition_pending` is not allowed to drift independently from canonical transition state,
  11. `UNKNOWN` never becomes `FAIL` merely due to absence of evidence,
  12. `FUTURE` requirement never blocks current transition,
  13. `NOT_APPLICABLE` requirement never blocks,
  14. `BLOCKED` requires verified applicable failure,
  15. `READY` requires all applicable blockers definitively satisfied,
  16. `level > 52` alone never means `COMPLETE`,
  17. `level > 52` does not erase an incomplete transition,
  18. Companion installed late can recognize an already-completed transition,
  19. `COMPLETE` survives restart and level advancement,
  20. Future progression requirements do not reopen completed Level-52 transition,
  21. M3 does not independently recompute M2 eligibility/delta semantics,
  22. State-machine evaluation is deterministic for identical persistent state and evidence.
- [ ] 6.3 Verify complete test and compliance suite passes: run `pytest tests/compliance/test_no_input_guard.py tests/rules/ tests/transition/ tests/state/ tests/build/`.