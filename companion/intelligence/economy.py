"""Economy advice and upgrade prioritization engine (DECOMMISSIONED per Blueprint Section 62).

Advanced economy ROI prioritization and currency investment guidance are explicitly
deferred by Blueprint Section 62. This module returns structured deferred feature notices.
"""

from __future__ import annotations

from typing import Any
from companion.intelligence.schema import EconomyPriority


def get_economy_deferred_notice() -> dict[str, Any]:
    """Return explicit deferred notice for economy optimization."""
    return {
        "status": "DEFERRED_BY_BLUEPRINT",
        "feature": "economy_prioritization",
        "blueprint_section": "62",
        "message": (
            "Advanced economy optimization and currency allocation ladders are deferred features "
            "per Blueprint Section 62."
        ),
    }


def evaluate_economy_priorities(
    character_level: int,
    current_resists_capped: bool,
    weapon_dps_lagging: bool,
    available_currency_tier: str = "low",
) -> list[EconomyPriority]:
    """Return empty list of economy priorities as feature is deferred."""
    return []
