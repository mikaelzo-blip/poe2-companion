"""Deterministic source manifest generator.

Produces byte-for-byte reproducible canonical manifest.json for validated
source snapshots. Dynamic run timestamps (such as extracted_at) are strictly
excluded from the canonical manifest and recorded only in anomaly reports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from companion.sources.unpacker import EXPECTED_STAGES
from companion.sources.validator import SourceValidationReport

MANIFEST_VERSION = "1.0"
TARGET_GAME_VERSION = "0.5.5"
BUILD_NAME = "Fubgun Flameblast Oil Grenade"
TOOL_VERSION = "0.1.0"


def generate_manifest(
    report: SourceValidationReport,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Generate canonical deterministic manifest dictionary and optionally save to disk.
    
    The output is byte-for-byte deterministic across repeated runs with identical source bytes.
    """
    # Sort files deterministically in progression stage order
    stage_order = {stage: idx for idx, stage in enumerate(EXPECTED_STAGES)}

    files: list[dict[str, Any]] = []
    sorted_snapshots = sorted(
        report.snapshots,
        key=lambda s: stage_order.get(s.logical_stage, 999),
    )

    for snap in sorted_snapshots:
        files.append({
            "logical_stage": snap.logical_stage,
            "filename": snap.filename,
            "sha256": snap.sha256,
            "byte_size": snap.byte_size,
            "validation_status": snap.validation_status,
        })

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "target_game_version": TARGET_GAME_VERSION,
        "build_name": BUILD_NAME,
        "tool_version": TOOL_VERSION,
        "files": files,
    }

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        # Deterministic serialization: UTF-8, 2 spaces indent, newline at EOF
        data = json.dumps(manifest, indent=2, sort_keys=False) + "\n"
        out.write_text(data, encoding="utf-8")

    return manifest
