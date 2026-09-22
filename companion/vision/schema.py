"""Data models and schemas for visual screen classification and stat extraction."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from companion.state.provenance import VerificationState


class ScreenType(str, Enum):
    """Categorical screen or panel identification."""

    CHARACTER_PANEL = "CHARACTER_PANEL"
    ITEM_TOOLTIP = "ITEM_TOOLTIP"
    SKILL_PANEL = "SKILL_PANEL"
    PASSIVE_SCREEN_TARGETED = "PASSIVE_SCREEN_TARGETED"
    UNKNOWN = "UNKNOWN"


class CharacterPanelStats(BaseModel):
    """Visible defensive attributes and resistances parsed from character panel."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    life: int | None = None
    mana: int | None = None
    spirit: int | None = None
    armour: int | None = None
    evasion: int | None = None
    fire_res: int | None = None
    cold_res: int | None = None
    lightning_res: int | None = None
    chaos_res: int | None = None


class VisionExtractionResult(BaseModel):
    """Result of visual extraction including semantic verification state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    screen_type: ScreenType
    stats: CharacterPanelStats | None = None
    verification_state: VerificationState = VerificationState.UNKNOWN
    confidence: float = 0.0
    raw_text: str | None = None
    captured_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
