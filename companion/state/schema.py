"""CharacterState v3 root schema and domain models.

Provides isolated per-character runtime persistence state with provenanced facts,
semantic verification, schema versioning, and Level-52 milestone transition records.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class CharacterState(BaseModel):
    """Pydantic model for CharacterState v2."""
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    schema_version: str = CURRENT_SCHEMA_VERSION
    character_id: str
    character_name: str
    character_class: str = "Mercenary"
    ascendancy: str = "Gemling Legionnaire"

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

    @field_validator("character_id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        return validate_character_id(v)

    @classmethod
    def create_initial(
        cls,
        character_id: str,
        character_name: str,
        character_class: str = "Mercenary",
        ascendancy: str = "Gemling Legionnaire",
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
