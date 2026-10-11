"""CharacterState v3 root schema and domain models.

Provides isolated per-character runtime persistence state with provenanced facts,
semantic verification, schema versioning, and Level-52 milestone transition records.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from companion.state.provenance import ProvenancedField, VerificationState
from companion.transition.state import Level52TransitionRecord

CHARACTER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
CURRENT_SCHEMA_VERSION = "3.0"


class InvalidCharacterIdError(ValueError):
    """Raised when a character ID violates the conservative allowed pattern."""
    pass


def validate_character_id(char_id: str) -> str:
    """Validate character ID against conservative format ^[a-zA-Z0-9_-]{1,64}$."""
    if not isinstance(char_id, str) or not CHARACTER_ID_PATTERN.match(char_id):
        raise InvalidCharacterIdError(
            f"Character ID '{char_id}' is invalid. Must be 1-64 alphanumeric characters, "
            f"hyphens, or underscores only without path traversal or separators."
        )
    return char_id


ASCENDANCY_CODES: dict[str, tuple[str, str]] = {
    "Ranger1": ("Ranger", "Deadeye"),
    "Ranger3": ("Ranger", "Pathfinder"),
    "Huntress1": ("Huntress", "Amazon"),
    "Huntress2": ("Huntress", "Spirit Walker"),
    "Huntress3": ("Huntress", "Ritualist"),
    "Warrior1": ("Warrior", "Titan"),
    "Warrior2": ("Warrior", "Warbringer"),
    "Warrior3": ("Warrior", "Smith of Kitava"),
    "Mercenary1": ("Mercenary", "Tactician"),
    "Mercenary2": ("Mercenary", "Witchhunter"),
    "Mercenary3": ("Mercenary", "Gemling Legionnaire"),
    "Druid1": ("Druid", "Oracle"),
    "Druid2": ("Druid", "Shaman"),
    "Witch1": ("Witch", "Infernalist"),
    "Witch2": ("Witch", "Blood Mage"),
    "Witch3": ("Witch", "Lich"),
    "Witch3b": ("Witch", "Abyssal Lich"),
    "Sorceress1": ("Sorceress", "Stormweaver"),
    "Sorceress2": ("Sorceress", "Chronomancer"),
    "Sorceress3": ("Sorceress", "Disciple of Varashta"),
    "Monk1": ("Monk", "Martial Artist"),
    "Monk2": ("Monk", "Invoker"),
    "Monk3": ("Monk", "Acolyte of Chayula"),
}


def split_class_code(value: str | None) -> tuple[str | None, str | None]:
    """Split PoE2 ascendancy code into (class, ascendancy).

    Strip; empty/None -> (None, None); a known code -> its (class, ascendancy);
    anything else -> (value, None).
    """
    if value is None:
        return (None, None)
    stripped = value.strip()
    if not stripped:
        return (None, None)
    if stripped in ASCENDANCY_CODES:
        return ASCENDANCY_CODES[stripped]
    return (stripped, None)


class CharacterState(BaseModel):
    """Pydantic model for CharacterState v2."""
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    schema_version: str = CURRENT_SCHEMA_VERSION
    character_id: str
    character_name: str
    character_class: str | None = None
    ascendancy: str | None = None

    level: ProvenancedField[int] = Field(
        default_factory=lambda: ProvenancedField[int].create(1, source="DEFAULT_INIT")
    )
    current_zone: ProvenancedField[str] = Field(
        default_factory=lambda: ProvenancedField[str].create("Unknown", source="DEFAULT_INIT")
    )
    current_act: ProvenancedField[int] = Field(
        default_factory=lambda: ProvenancedField[int].create(1, source="DEFAULT_INIT")
    )
    death_count: ProvenancedField[int] = Field(
        default_factory=lambda: ProvenancedField[int].create(0, source="DEFAULT_INIT")
    )
    equipped_weapon_set: ProvenancedField[int] = Field(
        default_factory=lambda: ProvenancedField[int].create(1, source="DEFAULT_INIT")
    )

    build_progression: dict[str, Any] = Field(
        default_factory=lambda: {
            "active_stage": "lvl 1-14",
            "target_build": "Fubgun Flameblast Oil Grenade",
        }
    )

    attributes: dict[str, ProvenancedField[int]] = Field(
        default_factory=lambda: {
            "strength": ProvenancedField[int].create(10, source="DEFAULT_INIT"),
            "dexterity": ProvenancedField[int].create(10, source="DEFAULT_INIT"),
            "intelligence": ProvenancedField[int].create(10, source="DEFAULT_INIT"),
        }
    )

    resistances: dict[str, ProvenancedField[int]] = Field(
        default_factory=lambda: {
            "fire": ProvenancedField[int].create(0, source="DEFAULT_INIT"),
            "cold": ProvenancedField[int].create(0, source="DEFAULT_INIT"),
            "lightning": ProvenancedField[int].create(0, source="DEFAULT_INIT"),
            "chaos": ProvenancedField[int].create(0, source="DEFAULT_INIT"),
        }
    )

    resources: dict[str, ProvenancedField[int]] = Field(
        default_factory=lambda: {
            "gold": ProvenancedField[int].create(0, source="DEFAULT_INIT"),
            "gcp": ProvenancedField[int].create(0, source="DEFAULT_INIT"),
        }
    )

    audit: dict[str, Any] = Field(
        default_factory=lambda: {
            "gear_last_completed": None,
            "skill_last_completed": None,
            "passive_checkpoint_last_completed": None,
        }
    )

    transition: Level52TransitionRecord | None = None

    session_active: bool = False
    last_observed_at: str | None = None

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="before")
    @classmethod
    def resolve_ascendancy_code(cls, data: Any) -> Any:
        """GGG reports the class as an ascendancy code ("Witch3"); the code is authoritative."""
        if isinstance(data, dict) and isinstance(data.get("character_class"), str):
            name, asc = split_class_code(data["character_class"])
            if asc is not None:
                data = {**data, "character_class": name, "ascendancy": asc}
        return data

    @field_validator("character_id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        return validate_character_id(v)

    def set_class(self, raw: str | None) -> None:
        """Update character class and ascendancy from a class or ascendancy code."""
        cls, asc = split_class_code(raw)
        if cls is None:
            return
        if asc is not None or cls != self.character_class:
            self.ascendancy = asc
        self.character_class = cls

    @classmethod
    def create_initial(
        cls,
        character_id: str,
        character_name: str,
        character_class: str | None = None,
        ascendancy: str | None = None,
    ) -> CharacterState:
        """Create a new validated character state."""
        validate_character_id(character_id)
        now_ts = datetime.now(timezone.utc).isoformat()
        return cls(
            character_id=character_id,
            character_name=character_name,
            character_class=character_class,
            ascendancy=ascendancy,
            created_at=now_ts,
            updated_at=now_ts,
        )
