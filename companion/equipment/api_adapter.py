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
        overwrite_conflicts: bool = False,
    ) -> tuple[EquippedLoadout | None, CharacterStatBaseline | None, list[str]]:
        warnings: list[str] = []

        if not self.is_api_available() and not raw_api_payload:
            warnings.append(
                f"API synchronization unavailable: OAuth 2.1 status is {self.oauth_status.value} (operating in MANUAL_ONLY mode)."
            )
            return None, None, warnings

        if not raw_api_payload or "error" in raw_api_payload:
            err_msg = raw_api_payload.get("error", "No response") if raw_api_payload else "Empty response"
            warnings.append(f"Character profile is private, hidden, or unavailable: {err_msg}")
            return None, None, warnings

        return self.parse_character_payload(
            raw_payload=raw_api_payload,
            character_id=character_id,
            current_loadout=current_loadout,
            overwrite_conflicts=overwrite_conflicts,
        )

    @classmethod
    def parse_character_payload(
        cls,
        raw_payload: dict[str, Any],
        character_id: str,
        current_loadout: EquippedLoadout | None = None,
        overwrite_conflicts: bool = False,
    ) -> tuple[EquippedLoadout | None, CharacterStatBaseline | None, list[str]]:
        warnings: list[str] = []
        eq_data = (
            raw_payload.get("items")
            or raw_payload.get("equipment")
            or raw_payload.get("character", {}).get("equipment")
            or raw_payload.get("character", {}).get("items")
            or []
        )
        if not eq_data:
            warnings.append("Payload does not contain any equipment or items.")
            return None, None, warnings

        loadout = EquippedLoadout.create_draft(character_id=character_id)
        if current_loadout:
            for s_val, entry in current_loadout.shared_slots.items():
                if entry and entry.item:
                    slot_enum = SlotType.from_str(s_val)
                    loadout.set_slot(
                        slot=slot_enum,
                        item=entry.item,
                        source=entry.source,
                        verification=entry.verification,
                        evidence_ref=entry.evidence_ref,
                    )
            for s_val, entry in current_loadout.weapon_set_1.items():
                if entry and entry.item:
                    slot_enum = SlotType.from_str(s_val)
                    loadout.set_slot(
                        slot=slot_enum,
                        item=entry.item,
                        source=entry.source,
                        weapon_set=WeaponSetContext.WEAPON_SET_1,
                        verification=entry.verification,
                        evidence_ref=entry.evidence_ref,
                    )
            for s_val, entry in current_loadout.weapon_set_2.items():
                if entry and entry.item:
                    slot_enum = SlotType.from_str(s_val)
                    loadout.set_slot(
                        slot=slot_enum,
                        item=entry.item,
                        source=entry.source,
                        weapon_set=WeaponSetContext.WEAPON_SET_2,
                        verification=entry.verification,
                        evidence_ref=entry.evidence_ref,
                    )

        # Mapping for GGG frameType
        frame_map = {0: "Normal", 1: "Magic", 2: "Rare", 3: "Unique", 9: "Relic"}

        # Ignored non-gear inventory locations
        ignored_invs = {"maininventory", "flask", "passivejewels"}

        for raw_item in eq_data:
            slot_name = raw_item.get("inventoryId") or raw_item.get("slot") or ""
            if not slot_name or slot_name.lower() in ignored_invs:
                continue

            normalized_inv = slot_name.lower().replace("-", "_").replace(" ", "_")
            weapon_set: WeaponSetContext | None = None

            if normalized_inv in ("weapon2", "weaponswap", "weapon_2", "weapon_2_swap", "weapon_1_swap", "set2_main_hand"):
                slot = SlotType.MAIN_HAND
                weapon_set = WeaponSetContext.WEAPON_SET_2
            elif normalized_inv in ("offhand2", "offhandswap", "offhand_2", "offhand_2_swap", "weapon_2_swap_offhand", "set2_off_hand"):
                slot = SlotType.OFF_HAND
                weapon_set = WeaponSetContext.WEAPON_SET_2
            elif normalized_inv in ("weapon", "weapon1", "mainhand", "main_hand"):
                slot = SlotType.MAIN_HAND
                weapon_set = WeaponSetContext.WEAPON_SET_1
            elif normalized_inv in ("offhand", "offhand1", "off_hand"):
                slot = SlotType.OFF_HAND
                weapon_set = WeaponSetContext.WEAPON_SET_1
            elif normalized_inv in ("ring", "ring1", "ring_1"):
                slot = SlotType.RING_1
            elif normalized_inv in ("ring2", "ring_2"):
                slot = SlotType.RING_2
            else:
                try:
                    slot = SlotType.from_str(slot_name)
                except ValueError:
                    continue

            name = raw_item.get("name", "").strip()
            base_type = raw_item.get("typeLine", "").strip()
            if not name and not base_type:
                continue
            if not name:
                name = base_type

            raw_frame = raw_item.get("frameType")
            rarity = raw_item.get("rarity") or frame_map.get(raw_frame, "Rare")

            lines = [
                f"Item Class: {base_type}",
                f"Rarity: {rarity}",
                name,
                base_type,
                "--------",
            ]

            # Add defenses/damage from properties
            for p in raw_item.get("properties", []):
                pname = p.get("name", "")
                vals = p.get("values", [])
                pval = vals[0][0] if vals and vals[0] else ""
                if pname in ("Armour", "Evasion Rating", "Energy Shield", "Physical Damage"):
                    lines.append(f"{pname}: {pval}")

            lines.append("--------")
            for m in raw_item.get("enchantMods", []):
                lines.append(f"{m} (enchant)")
            for m in raw_item.get("implicitMods", []):
                lines.append(f"{m} (implicit)")
            for m in raw_item.get("fracturedMods", []):
                lines.append(f"{m} (fractured)")
            for m in raw_item.get("explicitMods", []):
                lines.append(m)
            for m in raw_item.get("craftedMods", []):
                lines.append(m)
            for m in raw_item.get("runeMods", []):
                lines.append(f"{m} (rune)")

            try:
                item_candidate = parse_item_text(
                    "\n".join(lines),
                    target_slot=slot,
                    target_weapon_set=weapon_set,
                )
                new_entry = EquippedSlotEntry(
                    item=item_candidate,
                    slot=slot,
                    weapon_set=weapon_set,
                    source=BaselineSource.GGG_OFFICIAL_API,
                    verification=VerificationState.VERIFIED,
                )

                # Check conflict with existing manual loadout entry
                if current_loadout:
                    existing_entry = current_loadout.get_slot(slot, weapon_set=weapon_set)
                    if existing_entry:
                        if overwrite_conflicts:
                            if existing_entry.item.name != new_entry.item.name:
                                wset_label = f" ({weapon_set.value})" if weapon_set else ""
                                warnings.append(
                                    f"Slot {slot.value.upper()}{wset_label} diperbarui: '{existing_entry.item.name}' ditimpa dengan item resmi '{new_entry.item.name}'."
                                )
                        elif existing_entry.source != BaselineSource.GGG_OFFICIAL_API:
                            has_conflict, resolved_entry = detect_loadout_conflicts(existing_entry, new_entry)
                            if has_conflict:
                                wset_label = f" ({weapon_set.value})" if weapon_set else ""
                                warnings.append(
                                    f"Conflict detected in slot {slot.value.upper()}{wset_label}: manual '{existing_entry.item.name}' vs API '{new_entry.item.name}'."
                                )
                                new_entry = resolved_entry

                loadout.set_slot(
                    slot=slot,
                    item=new_entry.item,
                    source=new_entry.source,
                    weapon_set=weapon_set,
                    verification=new_entry.verification,
                    evidence_ref=new_entry.evidence_ref,
                )
            except Exception as item_err:
                warnings.append(f"Gagal memproses item pada slot {slot.value} ('{name}'): {item_err}")
                continue

        loadout.finalize(loadout_id=f"api_{character_id}")
        baseline = CharacterStatBaseline.create_empty(character_id=character_id, anchored_loadout_revision=1)
        return loadout, baseline, warnings
