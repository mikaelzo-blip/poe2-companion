"""PoB2 deeper passive tree comparison and patch drift detection."""

from __future__ import annotations

from typing import Iterable
from pydantic import BaseModel, ConfigDict, Field
from companion.api.schema import OfficialCharacterData


class Pob2ComparisonResult(BaseModel):
    """Result of comparing synchronized character passives against target PoB2 build."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    character_id: str
    matched_passives: list[str] = Field(default_factory=list)
    missing_passives: list[str] = Field(default_factory=list)
    extra_passives: list[str] = Field(default_factory=list)
    completion_ratio: float = 0.0
    patch_drift_detected: bool = False
    patch_drift_warning: str | None = None


def compare_character_with_pob2(
    character_data: OfficialCharacterData,
    target_passives: Iterable[str],
    expected_game_version: str = "0.1.0",
    expected_tree_revision: str | None = None,
) -> Pob2ComparisonResult:
    """Compare character's allocated passives with target PoB2 build and verify game version."""
    char_nodes = set(character_data.passives)
    target_nodes = set(target_passives)

    matched = sorted(list(char_nodes & target_nodes))
    missing = sorted(list(target_nodes - char_nodes))
    extra = sorted(list(char_nodes - target_nodes))

    ratio = len(matched) / max(1, len(target_nodes))

    # Detect patch drift from game and passive tree metadata.
    drift_reasons: list[str] = []
    if character_data.game_version != expected_game_version:
        drift_reasons.append(
            f"game version '{character_data.game_version}' differs from target '{expected_game_version}'"
        )
    if expected_tree_revision is not None and character_data.passive_tree_revision != expected_tree_revision:
        drift_reasons.append(
            f"passive tree revision '{character_data.passive_tree_revision}' differs from target '{expected_tree_revision}'"
        )

    drift_detected = bool(drift_reasons)
    drift_warning = None
    if drift_detected:
        drift_warning = "Build Patch Drift Detected: " + "; ".join(drift_reasons) + "."

    return Pob2ComparisonResult(
        character_id=character_data.character_id,
        matched_passives=matched,
        missing_passives=missing,
        extra_passives=extra,
        completion_ratio=ratio,
        patch_drift_detected=drift_detected,
        patch_drift_warning=drift_warning,
    )
