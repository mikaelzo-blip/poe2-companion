"""Declarative guide rule schema, metadata models, and typed enums.

Provides explicit rule representations decoupled from implicit heuristics.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RuleSourceType(str, Enum):
    """Authoritative or external provenance source of a rule."""
    BLUEPRINT_V2 = "BLUEPRINT_V2"
    FUBGUN_BUILD = "FUBGUN_BUILD"
    WRITTEN_GUIDE = "WRITTEN_GUIDE"
    POB2_REFERENCE = "POB2_REFERENCE"
    LABELED_INFERENCE = "LABELED_INFERENCE"
    PENDING_SOURCE_VERIFICATION = "PENDING_SOURCE_VERIFICATION"


class SourceVerificationStatus(str, Enum):
    """Verification trust status of the underlying rule source."""
    USABLE = "USABLE"
    PENDING_SOURCE_VERIFICATION = "PENDING_SOURCE_VERIFICATION"
    UNAVAILABLE = "UNAVAILABLE"


class ObservabilityMethod(str, Enum):
    """Observation paths through which rule compliance can be verified."""
    API = "API"
    GEAR_AUDIT = "GEAR_AUDIT"
    SKILL_AUDIT = "SKILL_AUDIT"
    PASSIVE_AUDIT = "PASSIVE_AUDIT"
    VISION = "VISION"
    MANUAL = "MANUAL"


class RuleEvaluationState(str, Enum):
    """Six-state semantic evaluation outcome for a rule."""
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    STALE = "STALE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"


class RequirementType(str, Enum):
    """Domain category of the condition being asserted."""
    EQUIPMENT = "EQUIPMENT"
    ITEM = "ITEM"
    SKILL = "SKILL"
    GEM = "GEM"
    PASSIVE = "PASSIVE"
    LEVEL = "LEVEL"
    STAT = "STAT"
    FLASK = "FLASK"
    GENERAL = "GENERAL"


class TransitionRuleRole(str, Enum):
    """Role a rule plays in governing progression transition state machines.

    Explicitly decoupled from RequirementType, observability methods, and provenance.
    """
    BLOCKING_REQUIREMENT = "BLOCKING_REQUIREMENT"
    COMPLETION_EVIDENCE = "COMPLETION_EVIDENCE"
    ADVISORY = "ADVISORY"
    PREPARATION = "PREPARATION"


SUPPORTED_OBSERVABILITY_METHODS: frozenset[ObservabilityMethod] = frozenset({
    ObservabilityMethod.API,
    ObservabilityMethod.GEAR_AUDIT,
    ObservabilityMethod.SKILL_AUDIT,
    ObservabilityMethod.PASSIVE_AUDIT,
})


class GuideRule(BaseModel):
    """Declarative specification of a build or transition rule."""
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    id: str
    name: str = ""
    description: str = ""
    notes: str | None = None
    provenance: RuleSourceType = RuleSourceType.BLUEPRINT_V2
    source_status: SourceVerificationStatus = Field(
        default=SourceVerificationStatus.USABLE,
        alias="status",
    )
    requirement_type: RequirementType = RequirementType.GENERAL
    transition_role: TransitionRuleRole = TransitionRuleRole.ADVISORY
    observable_via: list[ObservabilityMethod] = Field(default_factory=list)
    evaluable: bool = True
    trigger: dict[str, Any] | None = None
    min_level: int | None = None
    max_level: int | None = None
    stage: str | None = None
    expected: dict[str, Any] | None = None
    severity: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_and_validate(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Normalize status if present
        raw_status = data.get("status") or data.get("source_status")
        if raw_status is not None and isinstance(raw_status, str):
            status_upper = raw_status.upper()
            data["source_status"] = SourceVerificationStatus(status_upper)

        # Normalize provenance if string
        raw_prov = data.get("provenance")
        if raw_prov is not None and isinstance(raw_prov, str):
            data["provenance"] = RuleSourceType(raw_prov.upper())

        # Normalize requirement_type if string
        raw_req = data.get("requirement_type")
        if raw_req is not None and isinstance(raw_req, str):
            data["requirement_type"] = RequirementType(raw_req.upper())

        # Normalize transition_role if string
        raw_role = data.get("transition_role")
        if raw_role is not None and isinstance(raw_role, str):
            data["transition_role"] = TransitionRuleRole(raw_role.upper())

        # Extract trigger boundaries
        trigger = data.get("trigger")
        if isinstance(trigger, dict):
            if "min_level" in trigger and "min_level" not in data:
                data["min_level"] = trigger["min_level"]
            if "max_level" in trigger and "max_level" not in data:
                data["max_level"] = trigger["max_level"]
            if "stage" in trigger and "stage" not in data:
                data["stage"] = trigger["stage"]

        # Parse and normalize observable_via
        obs_input = data.get("observable_via", [])
        if isinstance(obs_input, (str, ObservabilityMethod)):
            obs_input = [obs_input]

        normalized_obs: list[ObservabilityMethod] = []
        for item in obs_input:
            if isinstance(item, str):
                normalized_obs.append(ObservabilityMethod(item.upper()))
            elif isinstance(item, ObservabilityMethod):
                normalized_obs.append(item)
            else:
                raise ValueError(f"Invalid observability method: {item}")
        data["observable_via"] = normalized_obs

        # Evaluate evaluable state based on observation paths
        has_supported_obs = any(m in SUPPORTED_OBSERVABILITY_METHODS for m in normalized_obs)
        if not has_supported_obs:
            data["evaluable"] = False
        elif "evaluable" not in data:
            data["evaluable"] = True

        return data

    @property
    def status(self) -> SourceVerificationStatus:
        """Alias property for source_status."""
        return self.source_status

    @property
    def source_type(self) -> RuleSourceType:
        """Alias property for provenance."""
        return self.provenance
