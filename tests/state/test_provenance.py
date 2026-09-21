"""Unit tests for provenance and semantic verification models."""

import pytest
from pydantic import ValidationError
from companion.state.provenance import (
    ProvenancedField,
    VerificationState,
)


def test_provenance_field_creation() -> None:
    field = ProvenancedField.create(
        value=15,
        source="LOG_CLIENT_TXT",
        verification_state=VerificationState.VERIFIED,
        evidence_refs=["hash:abc123"],
    )
    assert field.value == 15
    assert field.source == "LOG_CLIENT_TXT"
    assert field.verification_state == VerificationState.VERIFIED
    assert field.is_stale is False
    assert field.evidence_refs == ["hash:abc123"]


def test_rejects_invalid_or_numeric_verification_state() -> None:
    # Disallows numeric floats (e.g. 0.95 or 95)
    with pytest.raises(ValidationError):
        ProvenancedField[int](
            value=10,
            source="TEST",
            verification_state=0.95,  # type: ignore[arg-type]
        )

    with pytest.raises(ValidationError):
        ProvenancedField[int](
            value=10,
            source="TEST",
            verification_state="HIGH_CONFIDENCE",  # type: ignore[arg-type]
        )


def test_with_update_creates_new_instance() -> None:
    initial = ProvenancedField.create(value="Act 1", source="INIT")
    updated = initial.with_update(
        new_value="Act 2",
        source="ZONE_TRANSITION",
        verification_state=VerificationState.CORROBORATED,
        evidence_refs=["zone_id:act2_town"],
    )

    assert initial.value == "Act 1"
    assert updated.value == "Act 2"
    assert updated.source == "ZONE_TRANSITION"
    assert updated.verification_state == VerificationState.CORROBORATED
    assert updated.evidence_refs == ["zone_id:act2_town"]


def test_as_stale_marks_stale() -> None:
    field = ProvenancedField.create(
        value=52,
        source="TEST",
        verification_state=VerificationState.VERIFIED,
    )
    stale_field = field.as_stale()

    assert not field.is_stale
    assert stale_field.is_stale is True
    assert stale_field.verification_state == VerificationState.STALE
    assert stale_field.value == 52


def test_serialization_and_deserialization() -> None:
    field = ProvenancedField[int].create(
        value=75,
        source="INSPECT",
        verification_state=VerificationState.SINGLE_SOURCE,
    )
    json_data = field.model_dump_json()
    reloaded = ProvenancedField[int].model_validate_json(json_data)

    assert reloaded.value == 75
    assert reloaded.verification_state == VerificationState.SINGLE_SOURCE
