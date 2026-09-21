"""Shared centralized delta evaluation policy helper enforcing scoped ObservationCoverage."""

from __future__ import annotations

from enum import Enum
from companion.state.provenance import VerificationState
from companion.build.eligibility import EligibilityState
from companion.build.input import ObservationCoverage


class DeltaStatus(str, Enum):
    """Factual delta comparison status between player observation and build target."""
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    EXTRA = "EXTRA"
    UNKNOWN = "UNKNOWN"
    FUTURE = "FUTURE"
    EXPIRED = "EXPIRED"


class DeltaReason(str, Enum):
    """Structured rationale explaining non-standard or UNKNOWN delta statuses."""
    NONE = "NONE"
    STALE_PLAYER_STATE = "STALE_PLAYER_STATE"
    PARTIAL_PLAYER_OBSERVATION = "PARTIAL_PLAYER_OBSERVATION"
    OBSERVATION_COVERAGE_UNKNOWN = "OBSERVATION_COVERAGE_UNKNOWN"
    UNOBSERVED_SUBSYSTEM = "UNOBSERVED_SUBSYSTEM"
    INSUFFICIENT_EVIDENCE_RELIABILITY = "INSUFFICIENT_EVIDENCE_RELIABILITY"
    INELIGIBLE_LEVEL = "INELIGIBLE_LEVEL"


def evaluate_delta_item(
    target_eligibility: EligibilityState,
    player_observation_exists: bool,
    is_stale: bool,
    verification_state: VerificationState,
    observation_coverage: ObservationCoverage,
    is_entity_present: bool,
) -> tuple[DeltaStatus, DeltaReason]:
    """Shared deterministic delta evaluator across passives, skills, and equipment.

    Enforces the core MISSING Invariant:
    A target entity may evaluate to MISSING only when ALL five conditions are true:
    1. Target requirement is ACTIVE,
    2. Relevant player observation is fresh (not stale),
    3. Evidence quality is sufficient for definitive comparison (VERIFIED or CORROBORATED),
    4. Observation coverage for the relevant scope is COMPLETE, and
    5. The entity is confirmed absent from player state.

    Rules for other cases:
    - FUTURE target -> FUTURE with reason INELIGIBLE_LEVEL
    - EXPIRED target -> EXPIRED with reason INELIGIBLE_LEVEL
    - UNKNOWN target -> UNKNOWN with reason INELIGIBLE_LEVEL
    - Unobserved subsystem -> UNKNOWN with reason UNOBSERVED_SUBSYSTEM
    - Stale observation -> UNKNOWN with reason STALE_PLAYER_STATE
    - Insufficient evidence (UNKNOWN/CONFLICTING verification) -> UNKNOWN with reason INSUFFICIENT_EVIDENCE_RELIABILITY
    - Observation coverage UNKNOWN -> UNKNOWN with reason OBSERVATION_COVERAGE_UNKNOWN
    - Observation coverage PARTIAL -> if present: PRESENT; if absent: UNKNOWN with reason PARTIAL_PLAYER_OBSERVATION
    - Observation coverage COMPLETE:
        - If present: PRESENT with reason NONE
        - If absent: MISSING with reason NONE
    """
    if target_eligibility == EligibilityState.FUTURE:
        return DeltaStatus.FUTURE, DeltaReason.INELIGIBLE_LEVEL
    if target_eligibility == EligibilityState.EXPIRED:
        return DeltaStatus.EXPIRED, DeltaReason.INELIGIBLE_LEVEL
    if target_eligibility == EligibilityState.UNKNOWN:
        return DeltaStatus.UNKNOWN, DeltaReason.INELIGIBLE_LEVEL

    # Target requirement is ACTIVE
    if not player_observation_exists:
        return DeltaStatus.UNKNOWN, DeltaReason.UNOBSERVED_SUBSYSTEM

    if is_stale or verification_state == VerificationState.STALE:
        return DeltaStatus.UNKNOWN, DeltaReason.STALE_PLAYER_STATE

    if verification_state in (VerificationState.UNKNOWN, VerificationState.CONFLICTING):
        return DeltaStatus.UNKNOWN, DeltaReason.INSUFFICIENT_EVIDENCE_RELIABILITY

    # Check scoped observation coverage
    if observation_coverage == ObservationCoverage.UNKNOWN:
        return DeltaStatus.UNKNOWN, DeltaReason.OBSERVATION_COVERAGE_UNKNOWN

    if observation_coverage == ObservationCoverage.PARTIAL:
        if is_entity_present:
            return DeltaStatus.PRESENT, DeltaReason.NONE
        return DeltaStatus.UNKNOWN, DeltaReason.PARTIAL_PLAYER_OBSERVATION

    # Observation coverage is COMPLETE, verified, and fresh
    if is_entity_present:
        return DeltaStatus.PRESENT, DeltaReason.NONE

    # Definitive absence requires evidence quality sufficient for comparison (VERIFIED or CORROBORATED)
    if verification_state not in (VerificationState.VERIFIED, VerificationState.CORROBORATED):
        return DeltaStatus.UNKNOWN, DeltaReason.INSUFFICIENT_EVIDENCE_RELIABILITY

    return DeltaStatus.MISSING, DeltaReason.NONE
