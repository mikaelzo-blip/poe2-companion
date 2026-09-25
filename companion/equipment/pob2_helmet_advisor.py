"""PoB2 Helmet Advisor Adapter and Mathematical Delta Provider (Backward Compatibility Facade).

RESPONSIBILITY BOUNDARY:
- Subclasses Pob2EquipmentSession and PobEquipmentDelta to preserve the legacy helmet-specific
  API contract (current_helmet, current_helmet_name, simulate_candidate).
- Delegates simulation logic to the generic Pob2EquipmentSession foundation.
- Enforces async correctness: serialization/single-flight engine simulation, monotonically
  increasing candidate IDs, staleness tracking, and discarding stale candidate verdicts.
- Does NOT contain Fubgun campaign decision rules (rules live in fubgun_priorities.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from companion.equipment.pob2_equipment_advisor import (
    Pob2EquipmentSession,
    PobEquipmentDelta,
    resolve_pob2_backend_path,
)


class PobHelmetDelta(PobEquipmentDelta):
    """Mathematical stat deltas from PoB2 simulation for Helmets (backward-compatible facade)."""

    slot: str = "Helmet"


class Pob2HelmetSession(Pob2EquipmentSession):
    """Backward-compatible helmet adapter facade over Pob2EquipmentSession.

    Preserves existing helmet-specific methods and properties while delegating
    to the generic equipment session foundation.
    """

    @property
    def current_helmet(self) -> dict[str, Any] | None:
        """Equipped helmet item dictionary."""
        return self.equipped_items.get("Helmet")

    @property
    def current_helmet_name(self) -> str | None:
        """Name of the currently equipped helmet."""
        h = self.current_helmet
        if h and h.get("equipped"):
            return h.get("name")
        return None

    def simulate_candidate(
        self,
        candidate_id: int,
        candidate_raw: str,
        candidate_name: str = "",
    ) -> PobHelmetDelta | None:
        """Execute single-flight simulation for the candidate helmet on hot PoB2 build.

        Returns PobHelmetDelta if fresh and calculated, or None if stale or unavailable.
        """
        delta = self.simulate_item(
            slot="Helmet",
            raw_candidate=candidate_raw,
            candidate_id=candidate_id,
            candidate_name=candidate_name,
        )
        if delta is None:
            return None
        return PobHelmetDelta(**delta.model_dump())

