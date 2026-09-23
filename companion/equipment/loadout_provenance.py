"""Loadout provenance tracking and API conflict detection."""

from __future__ import annotations

from companion.state.provenance import VerificationState
from companion.equipment.loadout import EquippedSlotEntry


def detect_loadout_conflict(
    manual_entry: EquippedSlotEntry,
    api_entry: EquippedSlotEntry,
) -> tuple[bool, EquippedSlotEntry]:
    """Detect whether official API data contradicts manually ingested item.

    If conflicting, marks verification CONFLICTING and preserves both references.
    If matching, marks verification CORROBORATED.
    """
    m_item = manual_entry.item
    a_item = api_entry.item

    # Check match: name and base_type
    is_match = (m_item.name == a_item.name and m_item.base_type == a_item.base_type)

    if is_match:
        corroborated_entry = EquippedSlotEntry(
            item=manual_entry.item,
            slot=manual_entry.slot,
            weapon_set=manual_entry.weapon_set,
            source=manual_entry.source,
            observed_at=manual_entry.observed_at,
            verification=VerificationState.CORROBORATED,
            evidence_ref=f"manual:{manual_entry.evidence_ref};api:{api_entry.evidence_ref}",
            stale_after=manual_entry.stale_after,
        )
        return False, corroborated_entry

    conflicting_entry = EquippedSlotEntry(
        item=manual_entry.item,
        slot=manual_entry.slot,
        weapon_set=manual_entry.weapon_set,
        source=manual_entry.source,
        observed_at=manual_entry.observed_at,
        verification=VerificationState.CONFLICTING,
        evidence_ref=f"manual:{manual_entry.evidence_ref};api:{api_entry.evidence_ref}",
        stale_after=manual_entry.stale_after,
    )
    return True, conflicting_entry


detect_loadout_conflicts = detect_loadout_conflict

