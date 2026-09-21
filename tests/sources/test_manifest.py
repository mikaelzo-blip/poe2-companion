"""Unit tests for deterministic manifest generation and anomaly reporting."""

import json
from pathlib import Path
import yaml
from companion.sources.manifest import (
    BUILD_NAME,
    MANIFEST_VERSION,
    TARGET_GAME_VERSION,
    generate_manifest,
)
from companion.sources.reporter import generate_anomaly_reports
from companion.sources.unpacker import EXPECTED_STAGES
from companion.sources.validator import (
    AnomalyEntry,
    SnapshotValidationResult,
    SourceValidationReport,
)


def _build_dummy_report() -> SourceValidationReport:
    report = SourceValidationReport(
        total_snapshots=len(EXPECTED_STAGES),
        passed_count=len(EXPECTED_STAGES) - 1,
        anomalies_count=1,
    )
    # Put snapshots in reversed order to test sorting
    for stage in reversed(EXPECTED_STAGES):
        anomalies = []
        status = "PASS"
        if stage == "Endgame":
            status = "ANOMALIES"
            anomalies.append(
                AnomalyEntry(
                    stage=stage,
                    category="SOURCE_ANNOTATION",
                    symbol="Cast on Dodge",
                    details="meta-gem unsupported by official planner",
                    interval=[58, 100],
                )
            )
        report.snapshots.append(
            SnapshotValidationResult(
                logical_stage=stage,
                filename=f"{stage}.build",
                sha256=f"hash_{stage}",
                byte_size=1234,
                validation_status=status,
                anomalies=anomalies,
            )
        )
    return report


def test_manifest_is_byte_for_byte_deterministic(tmp_path: Path) -> None:
    report = _build_dummy_report()
    path1 = tmp_path / "manifest1.json"
    path2 = tmp_path / "manifest2.json"

    generate_manifest(report, output_path=path1)
    generate_manifest(report, output_path=path2)

    bytes1 = path1.read_bytes()
    bytes2 = path2.read_bytes()

    assert bytes1 == bytes2
    assert b"extracted_at" not in bytes1


def test_manifest_schema_and_ordering(tmp_path: Path) -> None:
    report = _build_dummy_report()
    path = tmp_path / "manifest.json"
    manifest = generate_manifest(report, output_path=path)

    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["target_game_version"] == TARGET_GAME_VERSION
    assert manifest["build_name"] == BUILD_NAME
    assert "extracted_at" not in manifest

    stages = [f["logical_stage"] for f in manifest["files"]]
    assert stages == list(EXPECTED_STAGES)


def test_anomaly_reports_generation(tmp_path: Path) -> None:
    report = _build_dummy_report()
    fixed_timestamp = "2026-09-21T12:00:00Z"

    json_path, md_path = generate_anomaly_reports(
        report,
        output_dir=tmp_path,
        execution_timestamp=fixed_timestamp,
    )

    assert json_path.is_file()
    assert md_path.is_file()

    json_content = json.loads(json_path.read_text(encoding="utf-8"))
    assert json_content["execution_timestamp"] == fixed_timestamp
    assert json_content["summary"]["total_snapshots"] == len(EXPECTED_STAGES)
    assert "additional_text_metrics" in json_content
    assert "raw_passive_duplicates" in json_content

    md_content = md_path.read_text(encoding="utf-8")
    assert fixed_timestamp in md_content
    assert "Cast on Dodge" in md_content
    assert "Additional Text & Planner Markup" in md_content
    assert "Raw Passive Duplicates" in md_content


def test_guide_rules_yaml_validity() -> None:
    rules_file = Path(__file__).resolve().parent.parent.parent / "data" / "source" / "guide_rules.yaml"
    assert rules_file.is_file()

    data = yaml.safe_load(rules_file.read_text(encoding="utf-8"))
    assert data["version"] == "1.0"
    assert data["target_game_version"] == "0.5.5"
    assert "provenance_legend" in data
    assert "BLUEPRINT_V2" in data["provenance_legend"]
    assert "PENDING_SOURCE_VERIFICATION" in data["provenance_legend"]

    rules = data["rules"]
    assert len(rules) >= 4
    provenances = {r["provenance"] for r in rules}
    assert "BLUEPRINT_V2" in provenances
    assert "PENDING_SOURCE_VERIFICATION" in provenances
