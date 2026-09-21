"""End-to-end integration test for M0 & M1 foundation."""

import json
from pathlib import Path
import pytest

from companion.compliance.no_input_guard import assert_no_input_compliance
from companion.sources.manifest import generate_manifest
from companion.sources.reporter import generate_anomaly_reports
from companion.sources.unpacker import EXPECTED_STAGES, unpack_source_archive
from companion.sources.validator import validate_snapshots_directory
from companion.state.provenance import VerificationState
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore

PRIMARY_ARCHIVE = Path(r"C:\Users\Fikri\Downloads\0.5.5 Fubgun Flameblast Oil Grenade.zip")


def test_full_m0_m1_e2e_lifecycle(tmp_path: Path) -> None:
    # 1. Verify static no-input compliance first
    project_companion = Path(__file__).resolve().parent.parent / "companion"
    assert_no_input_compliance(project_companion)

    # 2. Ingest source archive (use primary archive if present on host)
    archive_path = PRIMARY_ARCHIVE
    if not archive_path.is_file():
        pytest.skip(f"Primary archive not found at {archive_path}")

    builds_dir = tmp_path / "data" / "source" / "builds"
    snapshots = unpack_source_archive(archive_path, builds_dir)
    assert len(snapshots) == 9

    # 3. Validate sources
    report = validate_snapshots_directory(builds_dir)
    assert report.total_snapshots == 9
    assert report.failed_count == 0

    # 4. Generate deterministic manifest
    manifest_path = tmp_path / "data" / "source" / "manifest.json"
    manifest1 = generate_manifest(report, output_path=manifest_path)
    bytes1 = manifest_path.read_bytes()

    # Re-run manifest to verify byte-for-byte reproducibility
    manifest_path2 = tmp_path / "data" / "source" / "manifest2.json"
    manifest2 = generate_manifest(report, output_path=manifest_path2)
    bytes2 = manifest_path2.read_bytes()
    assert bytes1 == bytes2
    assert b"extracted_at" not in bytes1

    # 5. Generate anomaly reports
    reports_dir = tmp_path / "data" / "reports"
    json_rep, md_rep = generate_anomaly_reports(report, reports_dir)
    assert json_rep.is_file()
    assert md_rep.is_file()

    # 6. Initialize character state
    runtime_dir = tmp_path / "runtime"
    store = CharacterStateStore(runtime_dir)

    char = CharacterState.create_initial(
        character_id="fubgun_e2e_char",
        character_name="FubgunE2EHero",
    )
    store.save_character(char)
    store.set_active_character("fubgun_e2e_char")

    # 7. Update character state across progression milestones
    for lvl in [14, 32, 51, 52]:
        char.level = char.level.with_update(
            lvl,
            source="LOG_PROGRESSION",
            verification_state=VerificationState.VERIFIED,
        )
        store.save_character(char)

    # 8. Verify active character inspection
    active = store.get_active_character()
    assert active is not None
    assert active.character_id == "fubgun_e2e_char"
    assert active.level.value == 52
    assert active.level.verification_state == VerificationState.VERIFIED

    # 9. Verify rolling backup recovery
    canonical_file = store.get_character_path("fubgun_e2e_char")
    canonical_file.write_text("CORRUPTED_DISK_SECTOR", encoding="utf-8")

    recovered = store.load_character("fubgun_e2e_char")
    assert recovered.character_id == "fubgun_e2e_char"
    assert recovered.level.value in (32, 51, 52)
