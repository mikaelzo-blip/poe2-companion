"""GGG Official Character Window API adapter stubs, OAuth 2.1 gating, and conflict detection."""

from __future__ import annotations

from enum import Enum
from typing import Any
from companion.state.provenance import VerificationState
from companion.equipment.baseline import BaselineSource, CharacterStatBaseline
from companion.equipment.loadout import EquippedLoadout, EquippedSlotEntry
from companion.equipment.loadout_provenance import detect_loadout_conflicts
from companion.equipment.parser import parse_item_text
from companion.equipment.schema import ItemCandidate, SlotType, WeaponSetContext


class OAuthStatus(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    AUTHENTICATED = "AUTHENTICATED"
    EXPIRED = "EXPIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"


class OperationalMode(str, Enum):
    MANUAL_ONLY = "MANUAL_ONLY"
    API_ENRICHED = "API_ENRICHED"


class GGGCharacterAPIAdapter:
    def __init__(self, oauth_status: OAuthStatus = OAuthStatus.DISCONNECTED) -> None:
        self.oauth_status = oauth_status

    @property
    def operational_mode(self) -> OperationalMode:
        if self.oauth_status == OAuthStatus.AUTHENTICATED:
            return OperationalMode.API_ENRICHED
        return OperationalMode.MANUAL_ONLY

    def is_api_available(self) -> bool:
        return self.oauth_status == OAuthStatus.AUTHENTICATED

    def sync_character(
        self,
        account_name: str,
        character_id: str,
        current_loadout: EquippedLoadout | None = None,
        raw_api_payload: dict[str, Any] | None = None,
    ) -> tuple[EquippedLoadout | None, CharacterStatBaseline | None, list[str]]:
        warnings: list[str] = []

        if not self.is_api_available():
            warnings.append(
                f"API synchronization unavailable: OAuth 2.1 status is {self.oauth_status.value} (operating in MANUAL_ONLY mode)."
            )
            return None, None, warnings

        if not raw_api_payload or "error" in raw_api_payload:
            err_msg = raw_api_payload.get("error", "No response") if raw_api_payload else "Empty response"
            warnings.append(f"Character profile is private, hidden, or unavailable: {err_msg}")
            return None, None, warnings

        char_data = raw_api_payload.get("character", {})
        eq_data = raw_api_payload.get("equipment", [])

        loadout = EquippedLoadout.create_draft(character_id=character_id)

        for raw_item in eq_data:
            slot_name = raw_item.get("slot", "").lower()
            slot = SlotType.from_str(slot_name)
            name = raw_item.get("name", "Unknown Item")
            base_type = raw_item.get("typeLine", name)
            rarity = raw_item.get("rarity", "Rare")
            mods = raw_item.get("explicitMods", [])

            # Construct item text
            lines = [
                f"Item Class: {base_type}",
                f"Rarity: {rarity}",
                name,
                base_type,
                "--------",
            ]
            for m in mods:
                lines.append(m)

            item_candidate = parse_item_text("\n".join(lines), target_slot=slot)
            new_entry = EquippedSlotEntry(
                item=item_candidate,
                slot=slot,
                source=BaselineSource.GGG_OFFICIAL_API,
                verification=VerificationState.VERIFIED,
            )

            # Check conflict with existing manual loadout entry
            if current_loadout:
                existing_entry = current_loadout.get_slot(slot)
                if existing_entry:
                    has_conflict, resolved_entry = detect_loadout_conflicts(existing_entry, new_entry)
                    if has_conflict:
                        warnings.append(
                            f"Conflict detected in slot {slot.value.upper()}: manual '{existing_entry.item.name}' vs API '{new_entry.item.name}'."
                        )
                        new_entry = resolved_entry

            loadout.set_slot(
                slot=slot,
                item=new_entry.item,
                source=new_entry.source,
                verification=new_entry.verification,
                evidence_ref=new_entry.evidence_ref,
            )

        loadout.finalize(loadout_id=f"api_{character_id}")
        baseline = CharacterStatBaseline.create_empty(character_id=character_id, anchored_loadout_revision=1)

        return loadout, baseline, warnings
