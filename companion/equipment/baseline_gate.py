"""Baseline consistency gate verifying loadout revision anchoring and fingerprint."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from companion.equipment.baseline import CharacterStatBaseline

LEGACY_ANCHOR_REQUIRES_REBASELINE = "LEGACY_ANCHOR_REQUIRES_REBASELINE"


class BaselineConsistencyResult(BaseModel):
    """Result of evaluating baseline revision and fingerprint against loadout."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    is_consistent: bool
    reconciled_baseline: CharacterStatBaseline
    notices: list[str] = Field(default_factory=list)


def check_baseline_consistency(
    baseline: CharacterStatBaseline,
    current_loadout_revision: int,
    current_loadout_fingerprint: str | None = None,
) -> BaselineConsistencyResult:
    """Verify baseline.anchored_loadout_revision and fingerprint match current loadout.

    Consistency requires:
    1. Revision match: baseline.anchored_loadout_revision == current_loadout_revision
    2. Fingerprint presence: baseline.anchored_loadout_fingerprint is not None
       (legacy baselines lacking a fingerprint trigger LEGACY_ANCHOR_REQUIRES_REBASELINE)
    3. Fingerprint match: current_loadout_fingerprint is provided and matches baseline.anchored_loadout_fingerprint.
    """
    # 1. Revision mismatch
    if baseline.anchored_loadout_revision != current_loadout_revision:
        stale_baseline = baseline.mark_all_stale()
        notice = (
            f"Baseline was anchored to loadout revision {baseline.anchored_loadout_revision}, "
            f"but current loadout is revision {current_loadout_revision}. "
            "Character baseline stats marked STALE. Run 'companion gear baseline refresh' "
            "or 'companion gear baseline set' to re-anchor authoritative totals."
        )
        return BaselineConsistencyResult(
            is_consistent=False,
            reconciled_baseline=stale_baseline,
            notices=[notice],
        )

    # 2. Legacy baseline without fingerprint
    if baseline.anchored_loadout_fingerprint is None:
        stale_baseline = baseline.mark_all_stale()
        notice = (
            f"Legacy baseline lacks anchored loadout fingerprint ({LEGACY_ANCHOR_REQUIRES_REBASELINE}). "
            "Character baseline stats marked STALE. Re-establish baseline via "
            "'companion gear baseline set' or 'companion gear baseline refresh'."
        )
        return BaselineConsistencyResult(
            is_consistent=False,
            reconciled_baseline=stale_baseline,
            notices=[notice],
        )

    # 3. Current loadout fingerprint not provided
    if current_loadout_fingerprint is None:
        stale_baseline = baseline.mark_all_stale()
        notice = (
            "Current loadout fingerprint not provided; cannot verify baseline consistency. "
            "Character baseline stats marked STALE."
        )
        return BaselineConsistencyResult(
            is_consistent=False,
            reconciled_baseline=stale_baseline,
            notices=[notice],
        )

    # 4. Fingerprint mismatch
    if baseline.anchored_loadout_fingerprint != current_loadout_fingerprint:
        stale_baseline = baseline.mark_all_stale()
        notice = (
            f"Baseline loadout fingerprint mismatch (anchored: {baseline.anchored_loadout_fingerprint[:12]}..., "
            f"current: {current_loadout_fingerprint[:12]}...). "
            "Loadout content changed without clean re-anchor. Character baseline stats marked STALE."
        )
        return BaselineConsistencyResult(
            is_consistent=False,
            reconciled_baseline=stale_baseline,
            notices=[notice],
        )

    return BaselineConsistencyResult(
        is_consistent=True,
        reconciled_baseline=baseline,
        notices=[],
    )
