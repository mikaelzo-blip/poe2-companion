"""Build source validator and anomaly analyzer.

Inspects unpacked .build snapshots, verifies cryptographic hashes against raw disk
bytes, detects structural anomalies (such as the Cast on Dodge meta-gem), and
tracks passive deduplication contexts and interval shapes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from companion.sources.interval import IntervalKind
from companion.sources.models_normalized import (
    NormalizedBuild,
    WeaponSetContext,
    is_cast_on_dodge_id,
    normalize_build,
)
from companion.sources.models_raw import RawBuild
from companion.sources.unpacker import EXPECTED_STAGES, UnpackedSnapshot, match_logical_stage


@dataclass
class AnomalyEntry:
    """Represents a noted source anomaly or annotation."""
    stage: str
    category: str
    symbol: str
    details: str
    interval: Any = None


_PLANNER_MARKUP_REGEX = re.compile(
    r"\[/?(?:b|i|u|color|size|url|font|align|item|gem)[\s=\]]|<[a-zA-Z]+[^>]*>",
    re.IGNORECASE,
)


def has_official_planner_markup(text: str | None) -> bool:
    """Conservative check for official planner markup formatting syntax."""
    if not text:
        return False
    return bool(_PLANNER_MARKUP_REGEX.search(text))


@dataclass
class SnapshotValidationResult:
    """Validation outcome for a single .build snapshot."""
    logical_stage: str
    filename: str
    sha256: str
    byte_size: int
    validation_status: str  # PASS, ANOMALIES, FAIL
    raw_build: RawBuild | None = None
    normalized_build: NormalizedBuild | None = None
    anomalies: list[AnomalyEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SourceValidationReport:
    """Comprehensive validation report across all snapshot builds."""
    total_snapshots: int = 0
    passed_count: int = 0
    anomalies_count: int = 0
    failed_count: int = 0
    snapshots: list[SnapshotValidationResult] = field(default_factory=list)
    all_anomalies: list[AnomalyEntry] = field(default_factory=list)
    interval_shape_counts: dict[str, int] = field(
        default_factory=lambda: {
            "UNRESTRICTED": 0,
            "RANGE": 0,
            "UNRESOLVED_SINGLE_UINT": 0,
        }
    )
    weapon_set_counts: dict[str, int] = field(
        default_factory=lambda: {
            "DEFAULT_OR_SHARED": 0,
            "SPECIALISATION_1": 0,
            "SPECIALISATION_2": 0,
            "UNKNOWN_RESERVED": 0,
            "OTHER": 0,
        }
    )
    dual_weapon_set_passives: list[dict[str, Any]] = field(default_factory=list)
    cast_on_dodge_findings: list[dict[str, Any]] = field(default_factory=list)
    additional_text_count: int = 0
    recognized_markup_count: int = 0
    raw_passive_duplicate_count: int = 0
    raw_passive_duplicates: list[dict[str, Any]] = field(default_factory=list)


def validate_single_snapshot(
    file_path: Path,
    expected_stage: str | None = None,
) -> SnapshotValidationResult:
    """Validate a single .build file against raw and normalized models."""
    filename = file_path.name
    stage = expected_stage or match_logical_stage(filename) or filename

    try:
        raw_bytes = file_path.read_bytes()
        digest = hashlib.sha256(raw_bytes).hexdigest()
        byte_size = len(raw_bytes)
    except Exception as e:
        return SnapshotValidationResult(
            logical_stage=stage,
            filename=filename,
            sha256="",
            byte_size=0,
            validation_status="FAIL",
            errors=[f"Failed to read file: {e}"],
        )

    try:
        raw_data = json.loads(raw_bytes.decode("utf-8"))
        raw_build = RawBuild.model_validate(raw_data)
    except Exception as e:
        return SnapshotValidationResult(
            logical_stage=stage,
            filename=filename,
            sha256=digest,
            byte_size=byte_size,
            validation_status="FAIL",
            errors=[f"Failed to parse raw build JSON: {e}"],
        )

    anomalies: list[AnomalyEntry] = []
    warnings: list[str] = []

    try:
        norm_build = normalize_build(raw_build, logical_stage=stage)
        warnings.extend(norm_build.warnings)
    except Exception as e:
        return SnapshotValidationResult(
            logical_stage=stage,
            filename=filename,
            sha256=digest,
            byte_size=byte_size,
            validation_status="FAIL",
            raw_build=raw_build,
            errors=[f"Failed during build normalization: {e}"],
        )

    # Check for Cast on Dodge anomaly in skills and supports
    for s in norm_build.skills:
        if s.is_cast_on_dodge:
            anomalies.append(
                AnomalyEntry(
                    stage=stage,
                    category="SOURCE_ANNOTATION",
                    symbol=s.id,
                    details="meta-gem unsupported by official planner",
                    interval=s.level_interval.raw_value,
                )
            )
        for sup in s.support_skills:
            if sup.is_cast_on_dodge:
                anomalies.append(
                    AnomalyEntry(
                        stage=stage,
                        category="SOURCE_ANNOTATION",
                        symbol=sup.id,
                        details="meta-gem unsupported by official planner",
                        interval=sup.level_interval.raw_value,
                    )
                )

    # Check for extra unknown fields
    if norm_build.extra_fields:
        warnings.append(
            f"Extra top-level fields encountered: {list(norm_build.extra_fields.keys())}"
        )

    status = "FAIL" if warnings and any("Error" in w for w in warnings) else (
        "ANOMALIES" if anomalies or warnings else "PASS"
    )

    return SnapshotValidationResult(
        logical_stage=stage,
        filename=filename,
        sha256=digest,
        byte_size=byte_size,
        validation_status=status,
        raw_build=raw_build,
        normalized_build=norm_build,
        anomalies=anomalies,
        warnings=warnings,
    )


def validate_snapshots_directory(builds_dir: str | Path) -> SourceValidationReport:
    """Validate all expected .build files in the builds directory."""
    path = Path(builds_dir)
    report = SourceValidationReport()

    for stage in EXPECTED_STAGES:
        # Find matching file in directory
        matching = [f for f in path.glob("*.build") if match_logical_stage(f.name) == stage]
        if not matching:
            res = SnapshotValidationResult(
                logical_stage=stage,
                filename="",
                sha256="",
                byte_size=0,
                validation_status="FAIL",
                errors=[f"Missing required build file for stage '{stage}'"],
            )
            report.snapshots.append(res)
            report.failed_count += 1
            continue

        file_path = matching[0]
        res = validate_single_snapshot(file_path, expected_stage=stage)
        report.snapshots.append(res)
        report.total_snapshots += 1

        if res.validation_status == "PASS":
            report.passed_count += 1
        elif res.validation_status == "ANOMALIES":
            report.anomalies_count += 1
        else:
            report.failed_count += 1

        report.all_anomalies.extend(res.anomalies)

        # Aggregate metrics if normalized build available
        if res.normalized_build:
            norm = res.normalized_build

            # Collect interval shape statistics
            for s in norm.skills:
                report.interval_shape_counts[s.level_interval.kind.value] += 1
                for sup in s.support_skills:
                    report.interval_shape_counts[sup.level_interval.kind.value] += 1
            for inv in norm.inventory_slots:
                report.interval_shape_counts[inv.level_interval.kind.value] += 1
                if inv.additional_text and inv.additional_text.strip():
                    report.additional_text_count += 1
                    if has_official_planner_markup(inv.additional_text):
                        report.recognized_markup_count += 1

            # Weapon-set counts, raw duplicate passives, and multi-weapon set passives
            passive_contexts: dict[str, set[WeaponSetContext]] = {}
            for p in norm.passives:
                report.weapon_set_counts[p.weapon_set_context.value] += p.occurrences
                if p.occurrences > 1:
                    dups = p.occurrences - 1
                    report.raw_passive_duplicate_count += dups
                    report.raw_passive_duplicates.append({
                        "stage": stage,
                        "passive_id": p.passive_id,
                        "weapon_set_context": p.weapon_set_context.value,
                        "occurrences": p.occurrences,
                        "duplicate_count": dups,
                        "original_indices": p.original_indices,
                    })
                passive_contexts.setdefault(p.passive_id, set()).add(p.weapon_set_context)

            for pid, ctxs in passive_contexts.items():
                if len(ctxs) > 1:
                    report.dual_weapon_set_passives.append({
                        "stage": stage,
                        "passive_id": pid,
                        "contexts": [c.value for c in ctxs],
                    })

        for a in res.anomalies:
            if is_cast_on_dodge_id(a.symbol):
                report.cast_on_dodge_findings.append({
                    "stage": a.stage,
                    "symbol": a.symbol,
                    "interval": a.interval,
                    "details": a.details,
                })

    return report
