"""Authoritative CharacterStatBaseline domain models and provenanced facts."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Generic, TypeVar
from pydantic import BaseModel, ConfigDict, Field

from companion.state.provenance import VerificationState

T = TypeVar("T")


class BaselineSource(str, Enum):
    """Source origin of character baseline observations."""

    EXISTING_CHARACTER_STATE = "EXISTING_CHARACTER_STATE"
    GGG_OFFICIAL_API = "GGG_OFFICIAL_API"
    DERIVED_FROM_VERIFIED_COMPONENTS = "DERIVED_FROM_VERIFIED_COMPONENTS"
    DERIVED_CALCULATION = "DERIVED_CALCULATION"
    MANUAL_USER_INPUT = "MANUAL_USER_INPUT"
    MANUAL_SNAPSHOT = "MANUAL_SNAPSHOT"
    CLIPBOARD_ITEM_TEXT = "CLIPBOARD_ITEM_TEXT"
    UNKNOWN = "UNKNOWN"


class CharacterFact(BaseModel, Generic[T]):
    """A provenanced character stat fact. Value is None when UNKNOWN."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    value: T | None
    source: BaselineSource
    observed_at: str
    verification: VerificationState
    stale_after: str | None = None
    evidence_ref: str | None = None

    @property
    def is_known(self) -> bool:
        return self.value is not None and self.verification not in (
            VerificationState.UNKNOWN,
            VerificationState.STALE,
        )

    @classmethod
    def unknown(cls) -> CharacterFact[T]:
        now_iso = datetime.now(timezone.utc).isoformat()
        return cls(
            value=None,
            source=BaselineSource.UNKNOWN,
            observed_at=now_iso,
            verification=VerificationState.UNKNOWN,
        )

    @classmethod
    def create(
        cls,
        value: T | None,
        source: BaselineSource = BaselineSource.MANUAL_USER_INPUT,
        verification: VerificationState = VerificationState.VERIFIED,
        observed_at: str | None = None,
        evidence_ref: str | None = None,
    ) -> CharacterFact[T]:
        now_iso = observed_at or datetime.now(timezone.utc).isoformat()
        if value is None:
            return cls(
                value=None,
                source=BaselineSource.UNKNOWN,
                observed_at=now_iso,
                verification=VerificationState.UNKNOWN,
                evidence_ref=evidence_ref,
            )
        return cls(
            value=value,
            source=source,
            observed_at=now_iso,
            verification=verification,
            evidence_ref=evidence_ref,
        )

    def mark_stale(self) -> CharacterFact[T]:
        return CharacterFact(
            value=self.value,
            source=self.source,
            observed_at=self.observed_at,
            verification=VerificationState.STALE,
            stale_after=self.stale_after,
            evidence_ref=self.evidence_ref,
        )


class CharacterStatBaseline(BaseModel):
    """Complete character defensive, attribute, and mobility stat baseline."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    baseline_id: str
    character_id: str
    anchored_loadout_revision: int

    life: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    armour: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    evasion: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    energy_shield: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)

    raw_fire_res: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    effective_fire_res: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    max_fire_res: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    fire_overcap_buffer: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)

    raw_cold_res: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    effective_cold_res: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    max_cold_res: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    cold_overcap_buffer: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)

    raw_lightning_res: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    effective_lightning_res: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    max_lightning_res: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    lightning_overcap_buffer: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)

    raw_chaos_res: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    effective_chaos_res: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    max_chaos_res: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    chaos_overcap_buffer: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)

    strength: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    dexterity: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    intelligence: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)
    movement_speed: CharacterFact[int] = Field(default_factory=CharacterFact[int].unknown)

    observed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def fire_res_known(self) -> bool:
        return self.effective_fire_res.is_known

    @property
    def cold_res_known(self) -> bool:
        return self.effective_cold_res.is_known

    @property
    def lightning_res_known(self) -> bool:
        return self.effective_lightning_res.is_known

    @property
    def chaos_res_known(self) -> bool:
        return self.effective_chaos_res.is_known

    @property
    def fire_deficit(self) -> int:
        if self.effective_fire_res.is_known and self.effective_fire_res.value is not None:
            return max(0, 75 - self.effective_fire_res.value)
        return 0

    @property
    def cold_deficit(self) -> int:
        if self.effective_cold_res.is_known and self.effective_cold_res.value is not None:
            return max(0, 75 - self.effective_cold_res.value)
        return 0

    @property
    def lightning_deficit(self) -> int:
        if self.effective_lightning_res.is_known and self.effective_lightning_res.value is not None:
            return max(0, 75 - self.effective_lightning_res.value)
        return 0

    @property
    def chaos_deficit(self) -> int:
        if self.effective_chaos_res.is_known and self.effective_chaos_res.value is not None:
            return max(0, 0 - self.effective_chaos_res.value)
        return 0

    @classmethod
    def create_empty(
        cls,
        character_id: str,
        anchored_loadout_revision: int = 1,
        baseline_id: str | None = None,
    ) -> CharacterStatBaseline:
        return cls.create_partial(
            baseline_id=baseline_id or f"base_{character_id}",
            character_id=character_id,
            anchored_loadout_revision=anchored_loadout_revision,
        )

    @classmethod
    def create_partial(
        cls,
        baseline_id: str,
        character_id: str,
        anchored_loadout_revision: int,
        source: BaselineSource = BaselineSource.MANUAL_USER_INPUT,
        verification: VerificationState = VerificationState.VERIFIED,
        life: int | None = None,
        armour: int | None = None,
        evasion: int | None = None,
        energy_shield: int | None = None,
        fire_res: int | None = None,
        fire_raw: int | None = None,
        max_fire_res: int | None = None,
        cold_res: int | None = None,
        cold_raw: int | None = None,
        max_cold_res: int | None = None,
        lightning_res: int | None = None,
        lightning_raw: int | None = None,
        max_lightning_res: int | None = None,
        chaos_res: int | None = None,
        chaos_raw: int | None = None,
        max_chaos_res: int | None = None,
        strength: int | None = None,
        dexterity: int | None = None,
        intelligence: int | None = None,
        movement_speed: int | None = None,
    ) -> CharacterStatBaseline:
        now_iso = datetime.now(timezone.utc).isoformat()

        def make_fact(val: int | None) -> CharacterFact[int]:
            return CharacterFact[int].create(
                value=val,
                source=source if val is not None else BaselineSource.UNKNOWN,
                verification=verification if val is not None else VerificationState.UNKNOWN,
                observed_at=now_iso,
            )

        def make_res_facts(
            eff_val: int | None,
            raw_val: int | None,
            max_val: int | None,
        ) -> tuple[CharacterFact[int], CharacterFact[int], CharacterFact[int], CharacterFact[int]]:
            f_eff = make_fact(eff_val)
            f_raw = make_fact(raw_val)
            f_max = make_fact(max_val)

            # Compute overcap buffer if both raw and max (or effective) known
            overcap: int | None = None
            if raw_val is not None:
                cap_ref = max_val if max_val is not None else (eff_val if eff_val is not None else 75)
                overcap = max(0, raw_val - cap_ref)
            f_overcap = make_fact(overcap)

            return f_raw, f_eff, f_max, f_overcap

        f_raw_fire, f_eff_fire, f_max_fire, f_buf_fire = make_res_facts(fire_res, fire_raw, max_fire_res)
        f_raw_cold, f_eff_cold, f_max_cold, f_buf_cold = make_res_facts(cold_res, cold_raw, max_cold_res)
        f_raw_light, f_eff_light, f_max_light, f_buf_light = make_res_facts(lightning_res, lightning_raw, max_lightning_res)
        f_raw_chaos, f_eff_chaos, f_max_chaos, f_buf_chaos = make_res_facts(chaos_res, chaos_raw, max_chaos_res)

        return cls(
            baseline_id=baseline_id,
            character_id=character_id,
            anchored_loadout_revision=anchored_loadout_revision,
            life=make_fact(life),
            armour=make_fact(armour),
            evasion=make_fact(evasion),
            energy_shield=make_fact(energy_shield),
            raw_fire_res=f_raw_fire,
            effective_fire_res=f_eff_fire,
            max_fire_res=f_max_fire,
            fire_overcap_buffer=f_buf_fire,
            raw_cold_res=f_raw_cold,
            effective_cold_res=f_eff_cold,
            max_cold_res=f_max_cold,
            cold_overcap_buffer=f_buf_cold,
            raw_lightning_res=f_raw_light,
            effective_lightning_res=f_eff_light,
            max_lightning_res=f_max_light,
            lightning_overcap_buffer=f_buf_light,
            raw_chaos_res=f_raw_chaos,
            effective_chaos_res=f_eff_chaos,
            max_chaos_res=f_max_chaos,
            chaos_overcap_buffer=f_buf_chaos,
            strength=make_fact(strength),
            dexterity=make_fact(dexterity),
            intelligence=make_fact(intelligence),
            movement_speed=make_fact(movement_speed),
            observed_at=now_iso,
            updated_at=now_iso,
        )

    def mark_all_stale(self) -> CharacterStatBaseline:
        """Mark all known facts as STALE when revision mismatches."""
        return CharacterStatBaseline(
            baseline_id=self.baseline_id,
            character_id=self.character_id,
            anchored_loadout_revision=self.anchored_loadout_revision,
            life=self.life.mark_stale() if self.life.value is not None else self.life,
            armour=self.armour.mark_stale() if self.armour.value is not None else self.armour,
            evasion=self.evasion.mark_stale() if self.evasion.value is not None else self.evasion,
            energy_shield=self.energy_shield.mark_stale() if self.energy_shield.value is not None else self.energy_shield,
            raw_fire_res=self.raw_fire_res.mark_stale() if self.raw_fire_res.value is not None else self.raw_fire_res,
            effective_fire_res=self.effective_fire_res.mark_stale() if self.effective_fire_res.value is not None else self.effective_fire_res,
            max_fire_res=self.max_fire_res.mark_stale() if self.max_fire_res.value is not None else self.max_fire_res,
            fire_overcap_buffer=self.fire_overcap_buffer.mark_stale() if self.fire_overcap_buffer.value is not None else self.fire_overcap_buffer,
            raw_cold_res=self.raw_cold_res.mark_stale() if self.raw_cold_res.value is not None else self.raw_cold_res,
            effective_cold_res=self.effective_cold_res.mark_stale() if self.effective_cold_res.value is not None else self.effective_cold_res,
            max_cold_res=self.max_cold_res.mark_stale() if self.max_cold_res.value is not None else self.max_cold_res,
            cold_overcap_buffer=self.cold_overcap_buffer.mark_stale() if self.cold_overcap_buffer.value is not None else self.cold_overcap_buffer,
            raw_lightning_res=self.raw_lightning_res.mark_stale() if self.raw_lightning_res.value is not None else self.raw_lightning_res,
            effective_lightning_res=self.effective_lightning_res.mark_stale() if self.effective_lightning_res.value is not None else self.effective_lightning_res,
            max_lightning_res=self.max_lightning_res.mark_stale() if self.max_lightning_res.value is not None else self.max_lightning_res,
            lightning_overcap_buffer=self.lightning_overcap_buffer.mark_stale() if self.lightning_overcap_buffer.value is not None else self.lightning_overcap_buffer,
            raw_chaos_res=self.raw_chaos_res.mark_stale() if self.raw_chaos_res.value is not None else self.raw_chaos_res,
            effective_chaos_res=self.effective_chaos_res.mark_stale() if self.effective_chaos_res.value is not None else self.effective_chaos_res,
            max_chaos_res=self.max_chaos_res.mark_stale() if self.max_chaos_res.value is not None else self.max_chaos_res,
            chaos_overcap_buffer=self.chaos_overcap_buffer.mark_stale() if self.chaos_overcap_buffer.value is not None else self.chaos_overcap_buffer,
            strength=self.strength.mark_stale() if self.strength.value is not None else self.strength,
            dexterity=self.dexterity.mark_stale() if self.dexterity.value is not None else self.dexterity,
            intelligence=self.intelligence.mark_stale() if self.intelligence.value is not None else self.intelligence,
            movement_speed=self.movement_speed.mark_stale() if self.movement_speed.value is not None else self.movement_speed,
            observed_at=self.observed_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
