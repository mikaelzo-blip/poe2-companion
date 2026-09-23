"""EquippedLoadout domain models, draft ingestion, and revision management."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from companion.state.provenance import VerificationState
from companion.equipment.baseline import BaselineSource
from companion.equipment.schema import (
    ItemCandidate,
    SlotType,
    WeaponSetContext,
)

ALL_SHARED_SLOTS = [
    SlotType.HELMET,
    SlotType.BODY_ARMOUR,
    SlotType.GLOVES,
    SlotType.BOOTS,
    SlotType.AMULET,
    SlotType.RING_1,
    SlotType.RING_2,
    SlotType.BELT,
]

ALL_WEAPON_SLOTS = [
    SlotType.MAIN_HAND,
    SlotType.OFF_HAND,
]


class EquippedSlotEntry(BaseModel):
    """Entry for a single equipped slot in a loadout."""

    model_config = ConfigDict(frozen=True)

    item: ItemCandidate
    slot: SlotType
    weapon_set: WeaponSetContext | None = None
    source: BaselineSource = BaselineSource.CLIPBOARD_ITEM_TEXT
    observed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    verification: VerificationState = VerificationState.SINGLE_SOURCE
    evidence_ref: str | None = None
    stale_after: str | None = None


class EquippedLoadout(BaseModel):
    """Complete equipped loadout across shared equipment and dual weapon sets."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    loadout_id: str
    character_id: str
    revision: int = 1
    is_finalized: bool = False
    known_slots: list[SlotType] = Field(default_factory=list)
    unknown_slots: list[SlotType] = Field(default_factory=list)
    shared_slots: dict[str, EquippedSlotEntry | None] = Field(default_factory=dict)
    weapon_set_1: dict[str, EquippedSlotEntry | None] = Field(default_factory=dict)
    weapon_set_2: dict[str, EquippedSlotEntry | None] = Field(default_factory=dict)
    active_weapon_set: int = 1
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def create_draft(cls, character_id: str, loadout_id: str = "draft_loadout") -> EquippedLoadout:
        """Create a draft loadout ready for initial setup item capture."""
        now_iso = datetime.now(timezone.utc).isoformat()
        shared = {slot.value: None for slot in ALL_SHARED_SLOTS}
        wset1 = {slot.value: None for slot in ALL_WEAPON_SLOTS}
        wset2 = {slot.value: None for slot in ALL_WEAPON_SLOTS}
        all_slots = list(ALL_SHARED_SLOTS)
        return cls(
            loadout_id=loadout_id,
            character_id=character_id,
            revision=1,
            is_finalized=False,
            known_slots=[],
            unknown_slots=all_slots,
            shared_slots=shared,
            weapon_set_1=wset1,
            weapon_set_2=wset2,
            active_weapon_set=1,
            updated_at=now_iso,
        )

    def _update_known_unknown(self) -> None:
        known: list[SlotType] = []
        unknown: list[SlotType] = []

        for slot in ALL_SHARED_SLOTS:
            if self.shared_slots.get(slot.value) is not None:
                known.append(slot)
            else:
                unknown.append(slot)

        for slot in ALL_WEAPON_SLOTS:
            if self.weapon_set_1.get(slot.value) is not None or self.weapon_set_2.get(slot.value) is not None:
                if slot not in known:
                    known.append(slot)
            else:
                if slot not in unknown and slot not in known:
                    unknown.append(slot)

        self.known_slots = known
        self.unknown_slots = unknown

    def set_slot(
        self,
        slot: SlotType,
        item: ItemCandidate,
        source: BaselineSource = BaselineSource.CLIPBOARD_ITEM_TEXT,
        weapon_set: WeaponSetContext | None = None,
        verification: VerificationState = VerificationState.SINGLE_SOURCE,
        evidence_ref: str | None = None,
    ) -> None:
        """Assign an item to an equipped slot."""
        entry = EquippedSlotEntry(
            item=item,
            slot=slot,
            weapon_set=weapon_set,
            source=source,
            observed_at=datetime.now(timezone.utc).isoformat(),
            verification=verification,
            evidence_ref=evidence_ref,
        )

        if weapon_set == WeaponSetContext.WEAPON_SET_1 or slot in ALL_WEAPON_SLOTS and weapon_set is None:
            if weapon_set is None or weapon_set == WeaponSetContext.WEAPON_SET_1:
                self.weapon_set_1[slot.value] = entry
        elif weapon_set == WeaponSetContext.WEAPON_SET_2:
            self.weapon_set_2[slot.value] = entry
        else:
            self.shared_slots[slot.value] = entry

        self.updated_at = datetime.now(timezone.utc).isoformat()
        self._update_known_unknown()

    def get_slot(
        self,
        slot: SlotType,
        weapon_set: WeaponSetContext | None = None,
    ) -> EquippedSlotEntry | None:
        """Retrieve the item entry in the given slot."""
        if weapon_set == WeaponSetContext.WEAPON_SET_1:
            return self.weapon_set_1.get(slot.value)
        if weapon_set == WeaponSetContext.WEAPON_SET_2:
            return self.weapon_set_2.get(slot.value)
        if slot in ALL_WEAPON_SLOTS:
            return self.weapon_set_1.get(slot.value) or self.weapon_set_2.get(slot.value)
        return self.shared_slots.get(slot.value)

    def clear_slot(
        self,
        slot: SlotType,
        weapon_set: WeaponSetContext | None = None,
    ) -> None:
        """Clear an equipped slot."""
        if weapon_set == WeaponSetContext.WEAPON_SET_1:
            self.weapon_set_1[slot.value] = None
        elif weapon_set == WeaponSetContext.WEAPON_SET_2:
            self.weapon_set_2[slot.value] = None
        elif slot in ALL_WEAPON_SLOTS:
            self.weapon_set_1[slot.value] = None
            self.weapon_set_2[slot.value] = None
        else:
            self.shared_slots[slot.value] = None

        self.updated_at = datetime.now(timezone.utc).isoformat()
        self._update_known_unknown()

    def finalize(self, loadout_id: str | None = None) -> None:
        """Finalize the loadout, establishing revision 1 and stable known/unknown slots."""
        if loadout_id:
            self.loadout_id = loadout_id
        self.is_finalized = True
        self.revision = 1
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self._update_known_unknown()
