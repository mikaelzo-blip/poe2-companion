"""Shared domain models and schemas for expanded build intelligence."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class AdvisoryCategory(str, Enum):
    """Domain category for intelligence advisories."""
    SURVIVAL = "SURVIVAL"
    GEAR = "GEAR"
    TROUBLESHOOTING = "TROUBLESHOOTING"
    STORY = "STORY"
    ECONOMY = "ECONOMY"


class AdvisorySeverity(str, Enum):
    """Impact severity level for advisories."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ProvenanceCategory(str, Enum):
    """Mutually exclusive provenance classification for intelligence rules."""
    SOURCE_BACKED = "SOURCE_BACKED"
    LABELED_INFERENCE = "LABELED_INFERENCE"
    DEFERRED_BY_BLUEPRINT = "DEFERRED_BY_BLUEPRINT"
    REMOVE = "REMOVE"


class AdvisoryItem(BaseModel):
    """Discrete actionable recommendation or warning emitted by the advisory engine."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: AdvisoryCategory
    severity: AdvisorySeverity
    title: str
    description: str
    recommendation: str
    code: str
    context: dict[str, Any] = Field(default_factory=dict)
    is_inference: bool = False
    provenance: ProvenanceCategory = ProvenanceCategory.SOURCE_BACKED


class StoryQuest(BaseModel):
    """Permanent story progression quest reward tracking."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    quest_id: str
    act: int
    name: str
    reward_type: str  # "PASSIVE", "SPIRIT", "BANDIT"
    reward_detail: str
    completed: bool = False


class EconomyPriority(BaseModel):
    """Recommendation for currency investment and gear upgrade prioritization."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    priority_tier: int  # 1 = Highest ROI, 2 = High, 3 = Medium
    target_slot: str
    recommended_action: str
    estimated_cost: str
    roi_reason: str
