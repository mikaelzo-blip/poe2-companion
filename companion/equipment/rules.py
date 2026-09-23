"""Build-breaker domain models, rule schemas, and certainty states."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from companion.equipment.schema import NormalizedModifier


class RuleSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CONDITIONAL = "CONDITIONAL"
    BUILD_BREAKER = "BUILD_BREAKER"


class BuildBreakerCertainty(str, Enum):
    VERIFIED_SAFE = "VERIFIED_SAFE"
    VERIFIED_BUILD_BREAKER = "VERIFIED_BUILD_BREAKER"
    UNKNOWN_APPLICABILITY = "UNKNOWN_APPLICABILITY"


class BuildModifierFamily(str, Enum):
    FLAT_FIRE_ATTACK = "FLAT_FIRE_ATTACK"
    FLAT_FIRE_SPELL = "FLAT_FIRE_SPELL"
    EXTRA_FIRE_DAMAGE = "EXTRA_FIRE_DAMAGE"
    INCREASED_FIRE_PERCENT = "INCREASED_FIRE_PERCENT"
    FIRE_SPELL_LEVEL = "FIRE_SPELL_LEVEL"
    GENERIC_STAT = "GENERIC_STAT"
    UNKNOWN = "UNKNOWN"


class BuildProgressionStage(str, Enum):
    PRE_SWAP = "PRE_SWAP"
    EARLY_ENDGAME = "EARLY_ENDGAME"
    PINNACLE_ENDGAME = "PINNACLE_ENDGAME"


class BuildRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str
    name: str
    description: str
    severity: RuleSeverity = RuleSeverity.BUILD_BREAKER
    target_stages: list[BuildProgressionStage] = Field(default_factory=list)


class BuildBreakerEvaluation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    certainty: BuildBreakerCertainty = BuildBreakerCertainty.VERIFIED_SAFE
    severity: RuleSeverity = RuleSeverity.INFO
    rule_name: str = ""
    reason: str = ""
    violating_modifiers: list[NormalizedModifier] = Field(default_factory=list)
