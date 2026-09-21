"""Source anomaly and validation report generator.

Produces machine-readable JSON and human-readable Markdown reports containing
complete validation diagnostics, anomalies (such as Cast on Dodge), weapon-set
distributions, interval shape statistics, and operational execution metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from companion.sources.manifest import BUILD_NAME, TARGET_GAME_VERSION, TOOL_VERSION
from companion.sources.validator import SourceValidationReport


def generate_anomaly_reports(
    report: SourceValidationReport,
    output_dir: Path | str,
    execution_timestamp: str | None = None,
) -> tuple[Path, Path]:
    """Generate both JSON and Markdown anomaly reports in output_dir."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = execution_timestamp or datetime.now(timezone.utc).isoformat()

    json_path = out_dir / "m0_anomaly_report.json"
    md_path = out_dir / "m0_anomaly_report.md"

    # 1. Build JSON report data
    report_data: dict[str, Any] = {
        "report_type": "M0_SOURCE_VALIDATION_AND_ANOMALY_REPORT",
        "tool_version": TOOL_VERSION,
        "target_game_version": TARGET_GAME_VERSION,
        "build_name": BUILD_NAME,
        "execution_timestamp": ts,
        "summary": {
            "total_snapshots": report.total_snapshots,
            "passed_count": report.passed_count,
            "anomalies_count": report.anomalies_count,
            "failed_count": report.failed_count,
        },
        "interval_shapes": report.interval_shape_counts,
        "weapon_set_distribution": report.weapon_set_counts,
        "cast_on_dodge_findings": report.cast_on_dodge_findings,
        "dual_weapon_set_passives": report.dual_weapon_set_passives,
        "additional_text_metrics": {
            "total_non_empty_additional_text": report.additional_text_count,
            "recognized_markup_syntax_entries": report.recognized_markup_count,
        },
        "raw_passive_duplicates": {
            "total_duplicate_occurrences": report.raw_passive_duplicate_count,
            "total_duplicate_entries": len(report.raw_passive_duplicates),
            "duplicate_entries": report.raw_passive_duplicates,
        },
        "snapshots": [
            {
                "logical_stage": s.logical_stage,
                "filename": s.filename,
                "sha256": s.sha256,
                "byte_size": s.byte_size,
                "validation_status": s.validation_status,
                "anomalies": [
                    {
                        "category": a.category,
                        "symbol": a.symbol,
                        "details": a.details,
                        "interval": a.interval,
                    }
                    for a in s.anomalies
                ],
                "warnings": s.warnings,
                "errors": s.errors,
            }
            for s in report.snapshots
        ],
    }

    json_path.write_text(json.dumps(report_data, indent=2) + "\n", encoding="utf-8")

    # 2. Build Markdown report
    lines: list[str] = [
        f"# M0 Source Validation and Anomaly Report",
        "",
        f"- **Build Name**: {BUILD_NAME}",
        f"- **Game Version**: {TARGET_GAME_VERSION}",
        f"- **Tool Version**: {TOOL_VERSION}",
        f"- **Execution Timestamp (UTC)**: {ts}",
        "",
        "## Summary",
        "",
        f"- Total Snapshots: {report.total_snapshots}",
        f"- Status PASS: {report.passed_count}",
        f"- Status ANOMALIES: {report.anomalies_count}",
        f"- Status FAIL: {report.failed_count}",
        "",
        "## Level Interval Shapes",
        "",
        f"- Range `[min, max]`: {report.interval_shape_counts.get('RANGE', 0)}",
        f"- Unrestricted (omitted/None): {report.interval_shape_counts.get('UNRESTRICTED', 0)}",
        f"- Unresolved single uint: {report.interval_shape_counts.get('UNRESOLVED_SINGLE_UINT', 0)}",
        "",
        "## Weapon Set Distributions",
        "",
    ]

    for ws_name, count in report.weapon_set_counts.items():
        lines.append(f"- `{ws_name}`: {count} passive allocations")

    lines.extend([
        "",
        "## Cast on Dodge Meta-Gem Findings",
        "",
    ])
    if report.cast_on_dodge_findings:
        for cod in report.cast_on_dodge_findings:
            lines.append(
                f"- **{cod['stage']}**: Symbol `{cod['symbol']}`, Interval `{cod['interval']}` — *{cod['details']}*"
            )
    else:
        lines.append("- None detected.")

    lines.extend([
        "",
        "## Dual Weapon-Set Passives",
        "",
    ])
    if report.dual_weapon_set_passives:
        for d in report.dual_weapon_set_passives:
            lines.append(
                f"- **{d['stage']}**: Passive `{d['passive_id']}` appears in contexts: {', '.join(d['contexts'])}"
            )
    else:
        lines.append("- None detected.")

    lines.extend([
        "",
        "## Additional Text & Planner Markup",
        "",
        f"- Total Non-Empty `additional_text` Entries: {report.additional_text_count}",
        f"- Recognized Official Planner Markup Entries: {report.recognized_markup_count}",
        "",
        "## Raw Passive Duplicates",
        "",
        f"- Total Raw Duplicate Occurrences: {report.raw_passive_duplicate_count}",
        f"- Total Duplicated Raw Passive Entries: {len(report.raw_passive_duplicates)}",
    ])
    if report.raw_passive_duplicates:
        lines.append("")
        lines.append("| Stage | Passive ID | Context | Occurrences | Duplicate Count | Original Indices |")
        lines.append("|---|---|---|---|---|---|")
        for dup in report.raw_passive_duplicates:
            idx_str = ", ".join(str(i) for i in dup.get("original_indices", []))
            lines.append(
                f"| {dup['stage']} | `{dup['passive_id']}` | `{dup['weapon_set_context']}` | {dup['occurrences']} | {dup['duplicate_count']} | [{idx_str}] |"
            )

    lines.extend([
        "",
        "## Snapshots Detail",
        "",
        "| Stage | Status | SHA-256 | Size (bytes) | Anomalies | Warnings |",
        "|---|---|---|---|---|---|",
    ])

    for s in report.snapshots:
        anomaly_str = ", ".join(f"{a.symbol}" for a in s.anomalies) or "None"
        warning_str = f"{len(s.warnings)} warning(s)" if s.warnings else "None"
        short_hash = s.sha256[:12] + "..." if len(s.sha256) > 12 else s.sha256
        lines.append(
            f"| {s.logical_stage} | `{s.validation_status}` | `{short_hash}` | {s.byte_size} | {anomaly_str} | {warning_str} |"
        )

    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return json_path, md_path
