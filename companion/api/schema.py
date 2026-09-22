"""Pydantic schemas for official Path of Exile 2 Character API data."""

from __future__ import annotations

from typing import Any, Mapping
from pydantic import BaseModel, ConfigDict, Field


class OfficialItem(BaseModel):
    """Structured gear item from official API response."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: str
    name: str
    type_line: str
    rarity: str = "Rare"
    ilvl: int = 0
    requirements: dict[str, int] = Field(default_factory=dict)
    explicit_mods: list[str] = Field(default_factory=list)
    sockets: int = 0


class OfficialQuestStats(BaseModel):
    """Permanent story rewards completed according to official character API."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    permanent_passives: int = 0
    bandit_choice: str | None = None
    spirit_capacity: int = 0


class OfficialCharacterData(BaseModel):
    """Unified representation of official character synchronization."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    character_id: str
    name: str
    class_name: str
    level: int
    league: str
    game_version: str = "0.1.0"
    passive_tree_revision: str | None = None
    passives: list[str] = Field(default_factory=list)
    equipment: list[OfficialItem] = Field(default_factory=list)
    quest_stats: OfficialQuestStats = Field(default_factory=OfficialQuestStats)

    @classmethod
    def from_api_payload(cls, payload: Mapping[str, Any], character_id: str | None = None) -> "OfficialCharacterData":
        """Parse the normalized official character payload into a typed model."""
        if not isinstance(payload, Mapping):
            raise ValueError("official character payload must be a JSON object")
        metadata = payload.get("metadata")
        metadata_version = metadata.get("version") if isinstance(metadata, Mapping) else None
        if not isinstance(metadata, Mapping) or not isinstance(metadata_version, str) or not metadata_version.strip():
            raise ValueError("official character payload requires metadata.version")

        raw_items = payload.get("equipment", []) or []
        if not isinstance(raw_items, list):
            raise ValueError("official character payload equipment must be a list")
        equipment = [OfficialItem.model_validate(item) for item in raw_items]
        raw_quests = payload.get("quest_stats") or {}
        quest_stats = OfficialQuestStats.model_validate(raw_quests)
        raw_name = payload.get("name")
        raw_class = payload.get("class_name", payload.get("class"))
        raw_league = payload.get("league")
        level = payload.get("level")
        if (
            not isinstance(raw_name, str)
            or not raw_name.strip()
            or not isinstance(raw_class, str)
            or not raw_class.strip()
            or not isinstance(raw_league, str)
            or not raw_league.strip()
            or not isinstance(level, int)
            or isinstance(level, bool)
            or level < 1
        ):
            raise ValueError("official character payload is missing required metadata")

        raw_character_id = payload.get("character_id", character_id)
        if not isinstance(raw_character_id, str) or not raw_character_id.strip():
            raise ValueError("official character payload requires character_id")
        if character_id is not None and raw_character_id != character_id:
            raise ValueError("official character payload character_id does not match request")

        raw_game_version = payload.get("game_version", metadata_version)
        if not isinstance(raw_game_version, str) or not raw_game_version.strip():
            raise ValueError("official character payload requires game_version")
        raw_tree_revision = payload.get("passive_tree_revision", metadata.get("passive_tree_revision", metadata.get("tree_revision")))
        if raw_tree_revision is not None and not isinstance(raw_tree_revision, str):
            raise ValueError("official character payload passive tree revision must be a string")
        raw_passives = payload.get("passives", payload.get("passive_hashes", [])) or []
        if not isinstance(raw_passives, list) or not all(isinstance(passive, str) for passive in raw_passives):
            raise ValueError("official character payload passives must be a list of strings")

        return cls(
            character_id=raw_character_id,
            name=raw_name,
            class_name=raw_class,
            level=level,
            league=raw_league,
            game_version=raw_game_version,
            passive_tree_revision=raw_tree_revision,
            passives=raw_passives,
            equipment=equipment,
            quest_stats=quest_stats,
        )
