"""Schema versioning and lightweight migration dispatcher for CharacterState.

Upgrades older character state dictionaries to the current schema version (2.0)
and cleanly rejects unrecognized future versions.
"""

from __future__ import annotations

from typing import Any, Callable
from companion.state.provenance import ProvenancedField, VerificationState
from companion.state.schema import CURRENT_SCHEMA_VERSION

MigrationCallable = Callable[[dict[str, Any]], dict[str, Any]]


class UnsupportedSchemaVersionError(ValueError):
    """Raised when encountering an unrecognized or future schema version."""
    pass


def migrate_1_0_to_2_0(data: dict[str, Any]) -> dict[str, Any]:
    """Upgrade legacy v1.0 character state dict to v2.0 format with provenanced fields."""
    upgraded = dict(data)
    upgraded["schema_version"] = "2.0"

    # Wrap plain level into ProvenancedField if needed
    if "level" in upgraded and not isinstance(upgraded["level"], dict):
        upgraded["level"] = ProvenancedField[int].create(
            int(upgraded["level"]),
            source="MIGRATION_1_0",
            verification_state=VerificationState.CORROBORATED,
        ).model_dump()

    # Wrap plain current_zone if needed
    if "current_zone" in upgraded and not isinstance(upgraded["current_zone"], dict):
        upgraded["current_zone"] = ProvenancedField[str].create(
            str(upgraded["current_zone"]),
            source="MIGRATION_1_0",
            verification_state=VerificationState.CORROBORATED,
        ).model_dump()

    # Wrap plain current_act if needed
    if "current_act" in upgraded and not isinstance(upgraded["current_act"], dict):
        upgraded["current_act"] = ProvenancedField[int].create(
            int(upgraded["current_act"]),
            source="MIGRATION_1_0",
            verification_state=VerificationState.CORROBORATED,
        ).model_dump()

    return upgraded


MIGRATION_REGISTRY: dict[str, MigrationCallable] = {
    "1.0": migrate_1_0_to_2_0,
}


def apply_migrations(raw_data: dict[str, Any]) -> dict[str, Any]:
    """Apply sequential migrations up to CURRENT_SCHEMA_VERSION."""
    data = dict(raw_data)
    version = str(data.get("schema_version", "1.0"))

    if version == CURRENT_SCHEMA_VERSION:
        return data

    if version not in MIGRATION_REGISTRY:
        raise UnsupportedSchemaVersionError(
            f"Unsupported schema version '{version}'. Current supported version is '{CURRENT_SCHEMA_VERSION}'."
        )

    # Execute chain of migrations
    while version != CURRENT_SCHEMA_VERSION:
        if version not in MIGRATION_REGISTRY:
            raise UnsupportedSchemaVersionError(
                f"No migration path registered from schema version '{version}' to '{CURRENT_SCHEMA_VERSION}'."
            )
        data = MIGRATION_REGISTRY[version](data)
        version = str(data.get("schema_version"))

    return data
