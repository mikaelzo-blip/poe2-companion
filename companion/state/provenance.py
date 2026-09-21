"""Provenance models and semantic verification states for character state facts.

Every runtime observation is wrapped with origin metadata, observation timestamp,
semantic verification state, and audit evidence references.
Arbitrary numeric confidence percentages are strictly disallowed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Generic, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class VerificationState(str, Enum):
    """Semantic verification categories reflecting evidence strength."""
    VERIFIED = "VERIFIED"
    CORROBORATED = "CORROBORATED"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    CONFLICTING = "CONFLICTING"


class ProvenancedField(BaseModel, Generic[T]):
    """Wraps a single domain fact with source, timestamp, verification, and evidence."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    value: T
    source: str
    observed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    verification_state: VerificationState = VerificationState.UNKNOWN
    is_stale: bool = False
    evidence_refs: list[str] = Field(default_factory=list)

    @classmethod
    def create(
        cls,
        value: T,
        source: str = "SYSTEM_DEFAULT",
        verification_state: VerificationState = VerificationState.UNKNOWN,
        observed_at: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> ProvenancedField[T]:
        """Convenience constructor."""
        ts = observed_at or datetime.now(timezone.utc).isoformat()
        return cls(
            value=value,
            source=source,
            observed_at=ts,
            verification_state=verification_state,
            is_stale=False,
            evidence_refs=list(evidence_refs or []),
        )

    def with_update(
        self,
        new_value: T,
        source: str,
        verification_state: VerificationState,
        evidence_refs: list[str] | None = None,
    ) -> ProvenancedField[T]:
        """Return a new copy with updated value, source, and verification."""
        return ProvenancedField[T](
            value=new_value,
            source=source,
            observed_at=datetime.now(timezone.utc).isoformat(),
            verification_state=verification_state,
            is_stale=False,
            evidence_refs=list(evidence_refs or self.evidence_refs),
        )

    def as_stale(self) -> ProvenancedField[T]:
        """Return a new copy marked stale."""
        return ProvenancedField[T](
            value=self.value,
            source=self.source,
            observed_at=self.observed_at,
            verification_state=VerificationState.STALE,
            is_stale=True,
            evidence_refs=self.evidence_refs,
        )
