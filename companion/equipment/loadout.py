"""EquippedLoadout domain models, draft ingestion, and revision management."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
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


class FinalizedLoadoutMutationError(RuntimeError):
    """Raised when direct slot mutation is attempted on a finalized loadout bypassing revision transition."""


def compute_item_fingerprint(item: ItemCandidate | None) -> str:
    """Compute a deterministic fingerprint of decision-relevant item content."""
    if item is None:
        return "EMPTY"

    sorted_mods = []
    for m in item.modifiers:
        sorted_mods.append((
            m.modifier_type.value,
            m.scope.value,
            float(m.value),
            m.raw_text.strip().lower(),
            m.is_implicit,
            m.mechanic_id or "",
        ))
    sorted_mods.sort()

    payload = {
        "name": (item.name or "").strip().lower(),
        "base_type": (item.base_type or "").strip().lower(),
        "slot": item.slot.value,
        "slot_occupancy": item.slot_occupancy.value,
        "rarity": (item.rarity or "").strip().lower(),
        "item_level": item.item_level,
        "required_level": item.required_level,
        "required_str": item.required_str,
        "required_dex": item.required_dex,
        "required_int": item.required_int,
        "local_armour": item.local_armour,
        "local_evasion": item.local_evasion,
        "local_energy_shield": item.local_energy_shield,
        "modifiers": sorted_mods,
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_item_decision_equal(a: ItemCandidate | None, b: ItemCandidate | None) -> bool:
    """Return True if two items have identical decision-relevant representation."""
    return compute_item_fingerprint(a) == compute_item_fingerprint(b)


def compute_loadout_fingerprint(loadout: EquippedLoadout) -> str:
    """Compute deterministic fingerprint of decision-relevant loadout state.

    Includes:
    - Slot identity
    - Weapon-set context
    - Item decision-relevant identity and modifier content
    - Known vs unknown occupancy

    Excludes:
    - updated_at
    - loadout_id
    - character_id
    - revision
    - is_finalized
    - incidental ordering
    """
    shared = {
        slot.value: compute_item_fingerprint(
            loadout.shared_slots[slot.value].item
            if loadout.shared_slots.get(slot.value) is not None
            else None
        )
        for slot in sorted(ALL_SHARED_SLOTS, key=lambda s: s.value)
    }

    wset1 = {
        slot.value: compute_item_fingerprint(
            loadout.weapon_set_1[slot.value].item
            if loadout.weapon_set_1.get(slot.value) is not None
            else None
        )
        for slot in sorted(ALL_WEAPON_SLOTS, key=lambda s: s.value)
    }

    wset2 = {
        slot.value: compute_item_fingerprint(
            loadout.weapon_set_2[slot.value].item
            if loadout.weapon_set_2.get(slot.value) is not None
            else None
        )
        for slot in sorted(ALL_WEAPON_SLOTS, key=lambda s: s.value)
    }

    payload = {
        "shared_slots": shared,
        "weapon_set_1": wset1,
        "weapon_set_2": wset2,
        "active_weapon_set": loadout.active_weapon_set,
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    last_transition: Any = Field(default=None, exclude=True)

    def compute_fingerprint(self) -> str:
        """Compute deterministic fingerprint of decision-relevant loadout equipment."""
        return compute_loadout_fingerprint(self)

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

    def _raw_set_slot(
        self,
        slot: SlotType,
        item: ItemCandidate,
        source: BaselineSource = BaselineSource.CLIPBOARD_ITEM_TEXT,
        weapon_set: WeaponSetContext | None = None,
        verification: VerificationState = VerificationState.SINGLE_SOURCE,
        evidence_ref: str | None = None,
    ) -> None:
        """Raw internal slot assignment without finalization gate."""
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

    def _raw_clear_slot(
        self,
        slot: SlotType,
        weapon_set: WeaponSetContext | None = None,
    ) -> None:
        """Raw internal slot clear without finalization gate."""
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

    def set_slot(
        self,
        slot: SlotType,
        item: ItemCandidate,
        source: BaselineSource = BaselineSource.CLIPBOARD_ITEM_TEXT,
        weapon_set: WeaponSetContext | None = None,
        verification: VerificationState = VerificationState.SINGLE_SOURCE,
        evidence_ref: str | None = None,
    ) -> None:
        """Assign an item to an equipped slot.

        Raises FinalizedLoadoutMutationError if called directly on a finalized loadout.
        """
        if self.is_finalized:
            raise FinalizedLoadoutMutationError(
                f"Cannot mutate finalized loadout '{self.loadout_id}' (revision {self.revision}) directly via set_slot. "
                "Post-finalization changes must occur through controlled version transitions."
            )
        self._raw_set_slot(slot, item, source, weapon_set, verification, evidence_ref)

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
        """Clear an equipped slot.

        Raises FinalizedLoadoutMutationError if called directly on a finalized loadout.
        """
        if self.is_finalized:
            raise FinalizedLoadoutMutationError(
                f"Cannot mutate finalized loadout '{self.loadout_id}' (revision {self.revision}) directly via clear_slot. "
                "Post-finalization changes must occur through controlled version transitions."
            )
        self._raw_clear_slot(slot, weapon_set)

    def transition_slot(
        self,
        slot: SlotType,
        item: ItemCandidate,
        source: BaselineSource = BaselineSource.CLIPBOARD_ITEM_TEXT,
        weapon_set: WeaponSetContext | None = None,
        verification: VerificationState = VerificationState.SINGLE_SOURCE,
        evidence_ref: str | None = None,
    ) -> bool:
        """Execute a controlled versioned transition setting a slot.

        Returns True if a decision-relevant change occurred, False if no-op.
        If finalized and changed, increments revision exactly once.
        """
        existing = self.get_slot(slot, weapon_set=weapon_set)
        current_item = existing.item if existing else None
        if is_item_decision_equal(current_item, item):
            return False

        if self.is_finalized:
            self.revision += 1

        self._raw_set_slot(slot, item, source, weapon_set, verification, evidence_ref)
        return True

    def transition_clear_slot(
        self,
        slot: SlotType,
        weapon_set: WeaponSetContext | None = None,
    ) -> bool:
        """Execute a controlled versioned transition clearing a slot.

        Returns True if slot had an item cleared, False if already empty (no-op).
        If finalized and changed, increments revision exactly once.
        """
        existing = self.get_slot(slot, weapon_set=weapon_set)
        if existing is None or existing.item is None:
            return False

        if self.is_finalized:
            self.revision += 1

        self._raw_clear_slot(slot, weapon_set)
        return True

    def finalize(self, loadout_id: str | None = None) -> None:
        """Finalize the loadout, establishing revision 1 and stable known/unknown slots."""
        if loadout_id:
            self.loadout_id = loadout_id
        self.is_finalized = True
        self.revision = 1
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self._update_known_unknown()
