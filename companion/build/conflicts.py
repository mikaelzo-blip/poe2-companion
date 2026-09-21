"""Source precedence, availability tracking, and conflict record models."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class SourceAvailability(str, Enum):
    """Availability state of reference build sources."""
    USABLE = "USABLE"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    UNAVAILABLE = "UNAVAILABLE"


class ConflictRecord(BaseModel):
    """Structured representation of materially conflicting source or occurrence evidence."""
    model_config = ConfigDict(frozen=True)

    field_name: str
    conflicting_sources: list[str] = Field(default_factory=list)
    conflicting_values: list[Any] = Field(default_factory=list)
    status: str = "CONFLICTING_EVIDENCE"
    details: str | None = None


# Blueprint v2 Precedence Hierarchy (Slot 4 reserved for PoB2)
SOURCE_PRECEDENCE_HIERARCHY = [
    "WRITTEN_FUBGUN_RULE",
    "ACTIVE_BUILD",
    "ADJACENT_BUILD",
    "POB2_REFERENCE",  # Slot reserved; direct consumption NOT active in M2
    "LABELED_INFERENCE",
]
