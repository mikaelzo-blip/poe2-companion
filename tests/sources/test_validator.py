"""Unit tests for build validator and source anomaly analyzer."""

import json
from pathlib import Path
from companion.sources.unpacker import EXPECTED_STAGES
from companion.sources.validator import (
    has_official_planner_markup,
    validate_single_snapshot,
    validate_snapshots_directory,
)


def test_validator_detects_cast_on_dodge(tmp_path: Path) -> None:
    build_data = {
        "name": "Endgame",
        "skills": [
            {
                "id": "Cast on Dodge",
                "level_interval": [58, 100],
                "support_skills": [
                    {"id": "Flameblast", "level_interval": None}
                ],
            }
        ],
        "passives": [
            {"id": "node_1", "weapon_set": 1},
        ],
        "inventory_slots": [],
    }

    file_path = tmp_path / "Endgame - Fubgun.build"
    file_path.write_text(json.dumps(build_data), encoding="utf-8")

    res = validate_single_snapshot(file_path, expected_stage="Endgame")
    assert res.validation_status == "ANOMALIES"
    assert len(res.anomalies) == 1
    assert res.anomalies[0].symbol == "Cast on Dodge"
    assert res.anomalies[0].category == "SOURCE_ANNOTATION"
    assert res.anomalies[0].interval == [58, 100]


def test_validator_aggregates_across_directory(tmp_path: Path) -> None:
    # Generate 9 mock build files
    for stage in EXPECTED_STAGES:
        build_data = {
            "name": stage,
            "passives": [
                {"id": "p1", "weapon_set": 1 if "Swap" in stage else None},
                {"id": "p1", "weapon_set": 2 if "Swap" in stage else None},
            ],
            "skills": [
                {
                    "id": "SkillA",
                    "level_interval": [1, 50],
                    "support_skills": [{"id": "SupA", "level_interval": None}],
                }
            ],
            "inventory_slots": [
                {"inventory_id": "Helm", "slot_x": 0, "slot_y": 0, "level_interval": [1, 20]}
            ],
        }
        (tmp_path / f"{stage} - Fubgun.build").write_text(json.dumps(build_data), encoding="utf-8")

    report = validate_snapshots_directory(tmp_path)
    assert report.total_snapshots == 9
    assert report.failed_count == 0
    assert report.interval_shape_counts["RANGE"] > 0
    assert report.interval_shape_counts["UNRESTRICTED"] > 0
    assert len(report.snapshots) == 9


def test_markup_detection() -> None:
    assert not has_official_planner_markup("")
    assert not has_official_planner_markup(None)
    assert not has_official_planner_markup("Chiming Staff\n1. 209% increased Spell Damage")
    assert has_official_planner_markup("[b]Bold text[/b]")
    assert has_official_planner_markup("[color=#ff0000]Red[/color]")
    assert has_official_planner_markup("<div>HTML text</div>")


def test_validator_tracks_additional_text_and_raw_duplicates(tmp_path: Path) -> None:
    for stage in EXPECTED_STAGES:
        build_data = {
            "name": stage,
            "passives": [
                {"id": "node_dup", "weapon_set": None},
                {"id": "node_dup", "weapon_set": None},  # exact duplicate raw pair
                {"id": "node_unique", "weapon_set": 1},
            ],
            "skills": [],
            "inventory_slots": [
                {"inventory_id": "W1", "additional_text": "Plain stat line"},
                {"inventory_id": "W2", "additional_text": "[b]Markup stat line[/b]"},
                {"inventory_id": "W3", "additional_text": ""},
            ],
        }
        (tmp_path / f"{stage} - Fubgun.build").write_text(json.dumps(build_data), encoding="utf-8")

    report = validate_snapshots_directory(tmp_path)
    assert report.additional_text_count == 9 * 2  # 2 non-empty per stage
    assert report.recognized_markup_count == 9 * 1  # 1 with markup per stage
    assert report.raw_passive_duplicate_count == 9 * 1  # 1 duplicate occurrence per stage
    assert len(report.raw_passive_duplicates) == 9
