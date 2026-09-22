"""CLI integration tests for Milestone 8 gear auto-analysis subcommands."""

import json
from pathlib import Path
import pytest

from companion.cli import main

SAMPLE_BOOTS_TOOLTIP = """
Rarity: Rare
Storm Tread
Iron Greaves
--------
Requires Level 45, 52 Str
--------
Sockets: S S
--------
+45 to Maximum Life
+25% to Cold Resistance
30% increased Movement Speed
"""


def test_gear_status_cli_provenance_preservation(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from companion.gear.schema import ItemSlot
    from companion.gear.audit import record_slot_audit
    from companion.state.schema import CharacterState
    from companion.state.provenance import ProvenancedField, VerificationState
    from companion.state.store import CharacterStateStore

    char_id = "test_provenance_char"
    store = CharacterStateStore(tmp_path)
    store.save_character(CharacterState.create_initial(char_id, "TestName"))
    store.set_active_character(char_id)

    # Audit boots requiring 52 Str twice -> VERIFIED item
    record_slot_audit(tmp_path, char_id, ItemSlot.BOOTS, [SAMPLE_BOOTS_TOOLTIP, SAMPLE_BOOTS_TOOLTIP])

    # Case 1: Character attributes UNKNOWN (default unverified) -> NO false conflict
    code = main(["gear", "status", "--runtime", str(tmp_path), "--char", char_id, "--json"])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    unmet = [c for c in data["conflicts"] if c["conflict_type"] == "unmet_attribute"]
    assert len(unmet) == 0, f"Expected 0 unmet conflicts for unobserved attributes, got: {unmet}"

    # Case 2: Character has verified 30 Str (< 52) -> factual conflict
    state = store.load_character(char_id)
    verified_attrs = {
        "strength": ProvenancedField[int].create(30, source="character_sheet", verification_state=VerificationState.VERIFIED),
        "dexterity": ProvenancedField[int].create(50, source="character_sheet", verification_state=VerificationState.VERIFIED),
        "intelligence": ProvenancedField[int].create(50, source="character_sheet", verification_state=VerificationState.VERIFIED),
    }
    updated_state = state.model_copy(update={"attributes": verified_attrs})
    store.save_character(updated_state)

    code = main(["gear", "status", "--runtime", str(tmp_path), "--char", char_id, "--json"])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    unmet = [c for c in data["conflicts"] if c["conflict_type"] == "unmet_attribute"]
    assert len(unmet) == 1
    assert "Item requires 52 Str, but observed character has 30 Str." in unmet[0]["description"]



def test_gear_audit_cli(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main([
        "gear",
        "audit",
        "--slot",
        "boots",
        "--text",
        SAMPLE_BOOTS_TOOLTIP,
        "--runtime",
        str(tmp_path),
        "--json",
    ])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["slot"] == "boots"
    assert data["verification"].lower() in ("single_source", "verified")
    assert data["item_hash"] is not None


def test_gear_compare_cli(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main([
        "gear",
        "compare",
        "--slot",
        "boots",
        "--text",
        SAMPLE_BOOTS_TOOLTIP,
        "--runtime",
        str(tmp_path),
        "--json",
    ])
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "comparison" in data
    assert "advice" in data
