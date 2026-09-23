"""Baseline consistency gate verifying loadout revision anchoring."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from companion.equipment.baseline import CharacterStatBaseline


class BaselineConsistencyResult(BaseModel):
    """Result of evaluating baseline revision against loadout revision."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    is_consistent: bool
    reconciled_baseline: CharacterStatBaseline
    notices: list[str] = Field(default_factory=list)


def check_baseline_consistency(
    baseline: CharacterStatBaseline,
    current_loadout_revision: int,
) -> BaselineConsistencyResult:
    """Verify baseline.anchored_loadout_revision matches current_loadout_revision.

    If mismatched and not safely reconciled, marks affected stats STALE without
    blocking known item deltas or converting stats to zero.
    """
    if baseline.anchored_loadout_revision == current_loadout_revision:
        return BaselineConsistencyResult(
            is_consistent=True,
            reconciled_baseline=baseline,
            notices=[],
        )

    stale_baseline = baseline.mark_all_stale()
    notice = (
        f"Baseline was anchored to loadout revision {baseline.anchored_loadout_revision}, "
        f"but current loadout is revision {current_loadout_revision}. "
        f"Character baseline stats marked STALE. Run 'companion gear baseline refresh' "
        f"or take a fresh snapshot to re-anchor authoritative totals."
    )
    return BaselineConsistencyResult(
        is_consistent=False,
        reconciled_baseline=stale_baseline,
        notices=[notice],
    )
