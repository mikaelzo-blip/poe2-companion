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
    """Build progression stages for Fubgun Flameblast / Oil Grenade.

    Explicitly models the progression boundary between pre-swap and post-swap
    snapshots, independent of campaign/endgame classification.
    """

    # Canonical Fubgun snapshots
    LEVELING_1_14 = "LEVELING_1_14"
    LEVELING_15_32 = "LEVELING_15_32"
    LEVELING_33_51 = "LEVELING_33_51"
    SWAP_52 = "SWAP_52"
    LEVELING_53_68 = "LEVELING_53_68"
    LEVEL_85 = "LEVEL_85"
    ENDGAME = "ENDGAME"
    MAGEBLOOD = "MAGEBLOOD"
    DOT_CAP = "DOT_CAP"

    # Backward compatibility members (do not use for new code)
    PRE_SWAP = "PRE_SWAP"
    EARLY_ENDGAME = "EARLY_ENDGAME"
    PINNACLE_ENDGAME = "PINNACLE_ENDGAME"

    @classmethod
    def _missing_(cls, value: object) -> BuildProgressionStage | None:
        if isinstance(value, str):
            clean = value.strip().lower()
            mapping = {
                "lvl 1-14": cls.LEVELING_1_14,
                "lvl 15-32": cls.LEVELING_15_32,
                "lvl 33-51": cls.LEVELING_33_51,
                "lvl 52 swap": cls.SWAP_52,
                "lvl 52": cls.SWAP_52,
                "swap 52": cls.SWAP_52,
                "swap_52": cls.SWAP_52,
                "lvl 53-68": cls.LEVELING_53_68,
                "lvl 85": cls.LEVEL_85,
                "level 85": cls.LEVEL_85,
                "level_85": cls.LEVEL_85,
                "endgame": cls.ENDGAME,
                "mageblood": cls.MAGEBLOOD,
                "dot cap": cls.DOT_CAP,
                "dot_cap": cls.DOT_CAP,
                "leveling_1_14": cls.LEVELING_1_14,
                "leveling_15_32": cls.LEVELING_15_32,
                "leveling_33_51": cls.LEVELING_33_51,
                "leveling_53_68": cls.LEVELING_53_68,
                "pre_swap": cls.PRE_SWAP,
                "pre-swap": cls.PRE_SWAP,
                "early_endgame": cls.EARLY_ENDGAME,
                "early endgame": cls.EARLY_ENDGAME,
                "pinnacle_endgame": cls.PINNACLE_ENDGAME,
                "pinnacle endgame": cls.PINNACLE_ENDGAME,
            }
            if clean in mapping:
                return mapping[clean]
            upper_val = clean.upper()
            for member in cls:
                if member.value == upper_val:
                    return member
        return None

    @property
    def is_campaign(self) -> bool:
        """True if stage belongs to the campaign leveling acts (Acts 1-3+ / pre-maps)."""
        return self in (
            BuildProgressionStage.LEVELING_1_14,
            BuildProgressionStage.LEVELING_15_32,
            BuildProgressionStage.LEVELING_33_51,
            BuildProgressionStage.SWAP_52,
            BuildProgressionStage.LEVELING_53_68,
            BuildProgressionStage.PRE_SWAP,
        )

    @property
    def is_pre_swap(self) -> bool:
        """True if the character has not yet swapped to Oil Grenade (lvl 1-51)."""
        return self in (
            BuildProgressionStage.LEVELING_1_14,
            BuildProgressionStage.LEVELING_15_32,
            BuildProgressionStage.LEVELING_33_51,
            BuildProgressionStage.PRE_SWAP,
        )

    @property
    def is_post_swap(self) -> bool:
        """True if the character has swapped to Oil Grenade at or after lvl 52."""
        return self in (
            BuildProgressionStage.SWAP_52,
            BuildProgressionStage.LEVELING_53_68,
            BuildProgressionStage.LEVEL_85,
            BuildProgressionStage.ENDGAME,
            BuildProgressionStage.EARLY_ENDGAME,
            BuildProgressionStage.PINNACLE_ENDGAME,
            BuildProgressionStage.MAGEBLOOD,
            BuildProgressionStage.DOT_CAP,
        )


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
