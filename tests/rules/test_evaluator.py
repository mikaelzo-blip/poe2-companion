"""Unit tests for semantic rule evaluator and source verification gating."""

import pytest

from companion.rules.evaluator import (
    RuleEvaluationResult,
    RuleEvidence,
    evaluate_rule,
)
from companion.rules.schema import (
    GuideRule,
    ObservabilityMethod,
    RequirementType,
    RuleEvaluationState,
    RuleSourceType,
    SourceVerificationStatus,
    TransitionRuleRole,
)
from companion.state.provenance import VerificationState


def test_rule_evaluation_result_model_fields() -> None:
    """Verify RuleEvaluationResult schema, fields, and defaults."""
    res = RuleEvaluationResult(
        rule_id="RULE_01",
        state=RuleEvaluationState.PASS,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        source_status=SourceVerificationStatus.USABLE,
    )
    assert res.rule_id == "RULE_01"
    assert res.state == RuleEvaluationState.PASS
    assert res.reason is None
    assert res.details == {}
    assert res.transition_role == TransitionRuleRole.BLOCKING_REQUIREMENT
    assert res.source_status == SourceVerificationStatus.USABLE


def test_evaluate_rule_pass_state() -> None:
    """Verify condition satisfaction produces PASS for usable rule."""
    rule = GuideRule(
        id="RULE_PASS",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        observable_via=[ObservabilityMethod.API],
    )
    res_bool = evaluate_rule(rule, evidence=True)
    assert res_bool.state == RuleEvaluationState.PASS
    assert res_bool.rule_id == "RULE_PASS"
    assert res_bool.source_status == SourceVerificationStatus.USABLE
    assert res_bool.transition_role == TransitionRuleRole.BLOCKING_REQUIREMENT

    res_enum = evaluate_rule(rule, evidence=RuleEvaluationState.PASS)
    assert res_enum.state == RuleEvaluationState.PASS

    res_evidence = evaluate_rule(rule, evidence=RuleEvidence(satisfied=True))
    assert res_evidence.state == RuleEvaluationState.PASS


def test_evaluate_rule_fail_state() -> None:
    """Verify condition violation produces FAIL for usable rule."""
    rule = GuideRule(
        id="RULE_FAIL",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        observable_via=[ObservabilityMethod.API],
    )
    res_bool = evaluate_rule(rule, evidence=False)
    assert res_bool.state == RuleEvaluationState.FAIL
    assert res_bool.state != RuleEvaluationState.UNKNOWN
    assert res_bool.reason == "CONDITION_UNSATISFIED"

    res_enum = evaluate_rule(rule, evidence=RuleEvaluationState.FAIL)
    assert res_enum.state == RuleEvaluationState.FAIL

    res_evidence = evaluate_rule(rule, evidence=RuleEvidence(satisfied=False))
    assert res_evidence.state == RuleEvaluationState.FAIL


def test_absence_of_evidence_produces_unknown_never_fail() -> None:
    """Verify absence of evidence strictly evaluates to UNKNOWN, never FAIL."""
    rule = GuideRule(
        id="RULE_NO_EVIDENCE",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        observable_via=[ObservabilityMethod.API],
    )
    res_none = evaluate_rule(rule, evidence=None)
    assert res_none.state == RuleEvaluationState.UNKNOWN
    assert res_none.state != RuleEvaluationState.FAIL
    assert res_none.reason == "NO_EVIDENCE"

    res_dict_unobserved = evaluate_rule(rule, evidence={"is_observed": False})
    assert res_dict_unobserved.state == RuleEvaluationState.UNKNOWN
    assert res_dict_unobserved.state != RuleEvaluationState.FAIL

    res_evidence_unobserved = evaluate_rule(rule, evidence=RuleEvidence(is_observed=False))
    assert res_evidence_unobserved.state == RuleEvaluationState.UNKNOWN
    assert res_evidence_unobserved.state != RuleEvaluationState.FAIL


def test_stale_observation_produces_stale_never_fail() -> None:
    """Verify stale observation strictly evaluates to STALE, never FAIL."""
    rule = GuideRule(
        id="RULE_STALE",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        observable_via=[ObservabilityMethod.API],
    )
    res_enum = evaluate_rule(rule, evidence=RuleEvaluationState.STALE)
    assert res_enum.state == RuleEvaluationState.STALE
    assert res_enum.state != RuleEvaluationState.FAIL

    res_evidence = evaluate_rule(rule, evidence=RuleEvidence(satisfied=True, is_stale=True))
    assert res_evidence.state == RuleEvaluationState.STALE
    assert res_evidence.state != RuleEvaluationState.FAIL

    res_verif = evaluate_rule(rule, evidence=VerificationState.STALE)
    assert res_verif.state == RuleEvaluationState.STALE
    assert res_verif.state != RuleEvaluationState.FAIL

    res_dict = evaluate_rule(rule, evidence={"is_stale": True})
    assert res_dict.state == RuleEvaluationState.STALE
    assert res_dict.state != RuleEvaluationState.FAIL


def test_contradictory_evidence_produces_conflicting_never_fail() -> None:
    """Verify contradictory evidence evaluates to CONFLICTING_EVIDENCE, never FAIL."""
    rule = GuideRule(
        id="RULE_CONFLICT",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        observable_via=[ObservabilityMethod.API],
    )
    res_enum = evaluate_rule(rule, evidence=RuleEvaluationState.CONFLICTING_EVIDENCE)
    assert res_enum.state == RuleEvaluationState.CONFLICTING_EVIDENCE
    assert res_enum.state != RuleEvaluationState.FAIL

    res_evidence = evaluate_rule(rule, evidence=RuleEvidence(satisfied=True, is_conflicting=True))
    assert res_evidence.state == RuleEvaluationState.CONFLICTING_EVIDENCE
    assert res_evidence.state != RuleEvaluationState.FAIL

    res_verif = evaluate_rule(rule, evidence=VerificationState.CONFLICTING)
    assert res_verif.state == RuleEvaluationState.CONFLICTING_EVIDENCE
    assert res_verif.state != RuleEvaluationState.FAIL

    res_dict = evaluate_rule(rule, evidence={"is_conflicting": True})
    assert res_dict.state == RuleEvaluationState.CONFLICTING_EVIDENCE
    assert res_dict.state != RuleEvaluationState.FAIL


def test_outside_level_applicability_produces_not_applicable() -> None:
    """Verify character level outside trigger boundaries evaluates to NOT_APPLICABLE."""
    rule = GuideRule(
        id="RULE_LEVEL_BOUNDED",
        min_level=52,
        max_level=55,
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        observable_via=[ObservabilityMethod.API],
    )
    # Below min_level
    res_below = evaluate_rule(rule, evidence=True, character_level=50)
    assert res_below.state == RuleEvaluationState.NOT_APPLICABLE
    assert res_below.reason == "LEVEL_BELOW_MINIMUM"

    # Above max_level
    res_above = evaluate_rule(rule, evidence=True, character_level=56)
    assert res_above.state == RuleEvaluationState.NOT_APPLICABLE
    assert res_above.reason == "LEVEL_ABOVE_MAXIMUM"

    # At boundaries and inside -> evaluates evidence
    res_at_min = evaluate_rule(rule, evidence=True, character_level=52)
    assert res_at_min.state == RuleEvaluationState.PASS

    res_at_max = evaluate_rule(rule, evidence=False, character_level=55)
    assert res_at_max.state == RuleEvaluationState.FAIL


def test_inevaluable_rule_produces_unknown_with_reason() -> None:
    """Verify inevaluable rule returns UNKNOWN with reason INEVALUABLE_RULE."""
    rule = GuideRule(
        id="RULE_MANUAL_ONLY",
        observable_via=[ObservabilityMethod.MANUAL],
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.ADVISORY,
    )
    assert rule.evaluable is False

    res = evaluate_rule(rule, evidence=True)
    assert res.state == RuleEvaluationState.UNKNOWN
    assert res.reason == "INEVALUABLE_RULE"


def test_source_verification_gating_pending_source_verification() -> None:
    """Verify PENDING_SOURCE_VERIFICATION clamps to UNKNOWN even if condition satisfied or violated."""
    rule = GuideRule(
        id="FUBGUN_WRITTEN_GUIDE_GEAR_PRIORITIES",
        provenance=RuleSourceType.PENDING_SOURCE_VERIFICATION,
        source_status=SourceVerificationStatus.PENDING_SOURCE_VERIFICATION,
        transition_role=TransitionRuleRole.PREPARATION,
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    assert rule.evaluable is True

    # Even if condition is allegedly satisfied (True / PASS)
    res_pass = evaluate_rule(rule, evidence=True)
    assert res_pass.state == RuleEvaluationState.UNKNOWN
    assert res_pass.state != RuleEvaluationState.PASS
    assert res_pass.reason == "PENDING_SOURCE_VERIFICATION"
    assert res_pass.source_status == SourceVerificationStatus.PENDING_SOURCE_VERIFICATION

    # Even if condition is allegedly violated (False / FAIL)
    res_fail = evaluate_rule(rule, evidence=False)
    assert res_fail.state == RuleEvaluationState.UNKNOWN
    assert res_fail.state != RuleEvaluationState.FAIL
    assert res_fail.reason == "PENDING_SOURCE_VERIFICATION"

    # With stale evidence
    res_stale = evaluate_rule(rule, evidence=RuleEvaluationState.STALE)
    assert res_stale.state == RuleEvaluationState.UNKNOWN
    assert res_stale.reason == "PENDING_SOURCE_VERIFICATION"


def test_source_verification_gating_unavailable_status() -> None:
    """Verify UNAVAILABLE source status clamps to UNKNOWN with reason UNAVAILABLE_RULE_SOURCE."""
    rule = GuideRule(
        id="RULE_UNAVAILABLE",
        source_status=SourceVerificationStatus.UNAVAILABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        observable_via=[ObservabilityMethod.API],
    )
    res = evaluate_rule(rule, evidence=True)
    assert res.state == RuleEvaluationState.UNKNOWN
    assert res.state != RuleEvaluationState.PASS
    assert res.reason == "UNAVAILABLE_RULE_SOURCE"
    assert res.source_status == SourceVerificationStatus.UNAVAILABLE


def test_six_states_are_mutually_distinct_and_do_not_collapse() -> None:
    """Verify semantic distinction: UNKNOWN != FAIL, STALE != FAIL, CONFLICTING != FAIL."""
    rule = GuideRule(
        id="RULE_SEMANTICS",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        observable_via=[ObservabilityMethod.API],
    )

    r_pass = evaluate_rule(rule, evidence=True)
    r_fail = evaluate_rule(rule, evidence=False)
    r_unknown = evaluate_rule(rule, evidence=None)
    r_stale = evaluate_rule(rule, evidence=RuleEvaluationState.STALE)
    r_conflict = evaluate_rule(rule, evidence=RuleEvaluationState.CONFLICTING_EVIDENCE)
    r_na = evaluate_rule(rule, evidence=True, character_level=10) if rule.min_level else evaluate_rule(
        GuideRule(id="R_NA", min_level=50, observable_via=[ObservabilityMethod.API]),
        evidence=True,
        character_level=10,
    )

    states = {r_pass.state, r_fail.state, r_unknown.state, r_stale.state, r_conflict.state, r_na.state}
    assert len(states) == 6
    assert RuleEvaluationState.PASS in states
    assert RuleEvaluationState.FAIL in states
    assert RuleEvaluationState.UNKNOWN in states
    assert RuleEvaluationState.NOT_APPLICABLE in states
    assert RuleEvaluationState.STALE in states
    assert RuleEvaluationState.CONFLICTING_EVIDENCE in states

    # Invariant assertions: non-fail states never equal FAIL
    assert r_unknown.state != RuleEvaluationState.FAIL
    assert r_stale.state != RuleEvaluationState.FAIL
    assert r_conflict.state != RuleEvaluationState.FAIL
    assert r_na.state != RuleEvaluationState.FAIL


def test_evaluate_rule_flexible_evidence_string_and_dict() -> None:
    """Verify evaluate_rule accepts string literals and dictionaries cleanly."""
    rule = GuideRule(
        id="RULE_FLEX",
        source_status=SourceVerificationStatus.USABLE,
        transition_role=TransitionRuleRole.BLOCKING_REQUIREMENT,
        observable_via=[ObservabilityMethod.API],
    )
    # String literals
    assert evaluate_rule(rule, evidence="PASS").state == RuleEvaluationState.PASS
    assert evaluate_rule(rule, evidence="SATISFIED").state == RuleEvaluationState.PASS
    assert evaluate_rule(rule, evidence="FAIL").state == RuleEvaluationState.FAIL
    assert evaluate_rule(rule, evidence="UNSATISFIED").state == RuleEvaluationState.FAIL
    assert evaluate_rule(rule, evidence="STALE").state == RuleEvaluationState.STALE
    assert evaluate_rule(rule, evidence="CONFLICTING").state == RuleEvaluationState.CONFLICTING_EVIDENCE
    assert evaluate_rule(rule, evidence="UNKNOWN").state == RuleEvaluationState.UNKNOWN

    # Dictionaries
    assert evaluate_rule(rule, evidence={"satisfied": True}).state == RuleEvaluationState.PASS
    assert evaluate_rule(rule, evidence={"satisfied": False}).state == RuleEvaluationState.FAIL
    assert evaluate_rule(rule, evidence={"state": "PASS"}).state == RuleEvaluationState.PASS
    assert evaluate_rule(rule, evidence={"state": "FAIL"}).state == RuleEvaluationState.FAIL


def test_evaluate_rule_resolves_level_from_character_state() -> None:
    """Verify evaluate_rule automatically extracts character_level from CharacterState."""
    from companion.state.schema import CharacterState
    from companion.state.provenance import ProvenancedField

    rule = GuideRule(
        id="RULE_CHAR_STATE",
        min_level=52,
        observable_via=[ObservabilityMethod.API],
    )
    char_lvl_50 = CharacterState(
        character_id="char1",
        character_name="Merc",
        level=ProvenancedField[int].create(50, source="AUDIT"),
    )
    res_inapplicable = evaluate_rule(rule, evidence=True, character_state=char_lvl_50)
    assert res_inapplicable.state == RuleEvaluationState.NOT_APPLICABLE
    assert res_inapplicable.reason == "LEVEL_BELOW_MINIMUM"

    char_lvl_52 = CharacterState(
        character_id="char1",
        character_name="Merc",
        level=ProvenancedField[int].create(52, source="AUDIT"),
    )
    res_applicable = evaluate_rule(rule, evidence=True, character_state=char_lvl_52)
    assert res_applicable.state == RuleEvaluationState.PASS


def test_evaluate_rule_m2_delta_entry_duck_typing() -> None:
    """Verify evaluate_rule consumes M2 delta entries with status and reason."""
    from companion.build.equipment import EquipmentDeltaEntry
    from companion.build.policy import DeltaReason, DeltaStatus

    rule = GuideRule(
        id="RULE_DELTA",
        observable_via=[ObservabilityMethod.GEAR_AUDIT],
    )
    entry_present = EquipmentDeltaEntry(
        slot_id="MainHand",
        status=DeltaStatus.PRESENT,
    )
    assert evaluate_rule(rule, evidence=entry_present).state == RuleEvaluationState.PASS

    entry_missing = EquipmentDeltaEntry(
        slot_id="MainHand",
        status=DeltaStatus.MISSING,
    )
    assert evaluate_rule(rule, evidence=entry_missing).state == RuleEvaluationState.FAIL

    entry_stale = EquipmentDeltaEntry(
        slot_id="MainHand",
        status=DeltaStatus.UNKNOWN,
        reason=DeltaReason.STALE_PLAYER_STATE,
    )
    assert evaluate_rule(rule, evidence=entry_stale).state == RuleEvaluationState.STALE

    entry_future = EquipmentDeltaEntry(
        slot_id="MainHand",
        status=DeltaStatus.FUTURE,
        reason=DeltaReason.INELIGIBLE_LEVEL,
    )
    assert evaluate_rule(rule, evidence=entry_future).state == RuleEvaluationState.NOT_APPLICABLE


def test_evaluate_frozen_guide_rules() -> None:
    """Verify evaluate_rule works seamlessly with loaded frozen guide rules."""
    from companion.rules.loader import load_guide_rules

    rules = {r.id: r for r in load_guide_rules()}

    # SWAP_LVL_52: USABLE, min_level=52
    swap_rule = rules["SWAP_LVL_52"]
    assert evaluate_rule(swap_rule, evidence=True, character_level=51).state == RuleEvaluationState.NOT_APPLICABLE
    assert evaluate_rule(swap_rule, evidence=True, character_level=52).state == RuleEvaluationState.PASS
    assert evaluate_rule(swap_rule, evidence=False, character_level=52).state == RuleEvaluationState.FAIL
    assert evaluate_rule(swap_rule, evidence=None, character_level=52).state == RuleEvaluationState.UNKNOWN

    # GEM_CAST_ON_DODGE: USABLE, min_level=58
    cod_rule = rules["GEM_CAST_ON_DODGE"]
    assert evaluate_rule(cod_rule, evidence=True, character_level=52).state == RuleEvaluationState.NOT_APPLICABLE
    assert evaluate_rule(cod_rule, evidence=True, character_level=58).state == RuleEvaluationState.PASS

    # FUBGUN_WRITTEN_GUIDE_GEAR_PRIORITIES: PENDING_SOURCE_VERIFICATION, min_level=33, max_level=51
    gear_rule = rules["FUBGUN_WRITTEN_GUIDE_GEAR_PRIORITIES"]
    assert evaluate_rule(gear_rule, evidence=True, character_level=52).state == RuleEvaluationState.NOT_APPLICABLE
    # At level 50, within range, but clamped to UNKNOWN due to PENDING_SOURCE_VERIFICATION
    res_gear = evaluate_rule(gear_rule, evidence=True, character_level=50)
    assert res_gear.state == RuleEvaluationState.UNKNOWN
    assert res_gear.reason == "PENDING_SOURCE_VERIFICATION"

    # FUBGUN_WRITTEN_GUIDE_FLASK_SETUP: PENDING_SOURCE_VERIFICATION, observable_via=[MANUAL] -> inevaluable
    flask_rule = rules["FUBGUN_WRITTEN_GUIDE_FLASK_SETUP"]
    assert flask_rule.evaluable is False
    res_flask = evaluate_rule(flask_rule, evidence=True)
    assert res_flask.state == RuleEvaluationState.UNKNOWN
    assert res_flask.reason == "INEVALUABLE_RULE"


def test_companion_rules_reexports() -> None:
    """Verify companion.rules re-exports RuleEvaluationResult, RuleEvidence, and evaluate_rule."""
    import companion.rules as cr

    assert hasattr(cr, "RuleEvaluationResult")
    assert hasattr(cr, "RuleEvidence")
    assert hasattr(cr, "evaluate_rule")
    assert cr.RuleEvaluationResult is RuleEvaluationResult
    assert cr.RuleEvidence is RuleEvidence
    assert cr.evaluate_rule is evaluate_rule

