"""Rules module for declarative guide rules, metadata schemas, and loaders."""

from companion.rules.evaluator import (
    RuleEvaluationResult,
    RuleEvidence,
    evaluate_rule,
)
from companion.rules.loader import DEFAULT_GUIDE_RULES_PATH, load_guide_rules
from companion.rules.schema import (
    SUPPORTED_OBSERVABILITY_METHODS,
    GuideRule,
    ObservabilityMethod,
    RequirementType,
    RuleEvaluationState,
    RuleSourceType,
    SourceVerificationStatus,
    TransitionRuleRole,
)

__all__ = [
    "DEFAULT_GUIDE_RULES_PATH",
    "SUPPORTED_OBSERVABILITY_METHODS",
    "GuideRule",
    "ObservabilityMethod",
    "RequirementType",
    "RuleEvaluationResult",
    "RuleEvaluationState",
    "RuleEvidence",
    "RuleSourceType",
    "SourceVerificationStatus",
    "TransitionRuleRole",
    "evaluate_rule",
    "load_guide_rules",
]
