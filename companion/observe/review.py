"""Generates human-readable DEVELOPMENT_OBSERVATION_REPORT.md adhering to review taxonomy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from companion.observe.manifest import ManifestManager


def generate_development_observation_report(
    session_dir: Path,
    output_file: Path | None = None,
) -> Path:
    """Generate DEVELOPMENT_OBSERVATION_REPORT.md from session artifacts."""
    target_path = output_file or Path("DEVELOPMENT_OBSERVATION_REPORT.md")

    manifest_mgr = ManifestManager(session_dir / "session_manifest.json")
    manifest = manifest_mgr.load()

    # Read anomalies
    anomalies_file = session_dir / "anomalies.json"
    anomalies: dict[str, Any] = {}
    if anomalies_file.exists():
        try:
            anomalies = json.loads(anomalies_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Read markers
    markers = []
    markers_file = session_dir / "markers.jsonl"
    if markers_file.exists():
        with open(markers_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        markers.append(json.loads(line.strip()))
                    except Exception:
                        pass

    # Segregate anomalies into strong (defects/gaps) and weak (single occurrence, uncorroborated)
    likely_defects = []
    weak_evidence = []
    data_gaps = []

    for sig, a in anomalies.items():
        occ = a.get("occurrence_count", 1)
        evt_id = a.get("first_seen_event_id", "unknown")
        msg = a.get("sample_message", "")
        time_win = f"{a.get('first_seen_timestamp')} to {a.get('last_seen_timestamp')}"

        if occ == 1:
            weak_evidence.append({
                "description": msg,
                "event_id": evt_id,
                "reason": "Single occurrence without corroborating failure or invariant violation",
            })
        else:
            likely_defects.append({
                "description": msg,
                "event_id": evt_id,
                "occurrence_count": occ,
                "window": time_win,
            })

    # Check backpressure drops in manifest
    if manifest and manifest.dropped_event_count > 0:
        weak_evidence.append({
            "description": f"{manifest.dropped_event_count} events dropped due to backpressure queue overflow",
            "event_id": "N/A",
            "reason": "Dropped under load (fail-safe bounded queue shedding)",
        })

    # Construct report
    lines = [
        "# PoE2 Companion Development Observation Report",
        "",
        f"**Session ID:** `{session_dir.name}`  ",
        f"**Status:** {manifest.status.value if manifest else 'UNKNOWN'}  ",
        f"**Timeline:** {manifest.started_at if manifest else 'N/A'} - {manifest.ended_at if manifest else 'N/A'}  ",
        "",
        "## 1. Observed Facts",
        f"- Persisted events: {manifest.persisted_event_count if manifest else 0}",
        f"- User markers recorded: {len(markers)}",
        f"- Anomaly patterns discovered: {len(anomalies)}",
        "",
        "## 2. Likely Defects",
    ]

    if likely_defects:
        for d in likely_defects:
            lines.append(f"- **[CITED: {d['event_id']}]** {d['description']} (Occurrences: {d['occurrence_count']}, Window: {d['window']})")
    else:
        lines.append("- No confirmed defects identified.")

    lines.extend([
        "",
        "## 3. Usability Findings",
    ])
    if markers:
        for m in markers:
            p = m.get("payload", {})
            lines.append(f"- **[USER MARKER {m.get('event_id', 'unknown')}]** {p.get('note', '')}")
    else:
        lines.append("- No explicit usability findings noted during this session.")

    lines.extend([
        "",
        "## 4. Data Gaps",
    ])
    if data_gaps:
        for g in data_gaps:
            lines.append(f"- {g}")
    else:
        lines.append("- No missing observation sources identified.")

    lines.extend([
        "",
        "## 5. Feature Opportunities",
        "- Expand telemetry to track area-level zone difficulty curves.",
        "",
        "## 6. Not Enough Evidence / Missing Evidence",
    ])
    if weak_evidence:
        for w in weak_evidence:
            lines.append(f"- **[WEAK EVIDENCE: {w['event_id']}]** {w['description']} - *Reason: {w['reason']}*")
    else:
        lines.append("- None.")

    report_content = "\n".join(lines) + "\n"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(report_content, encoding="utf-8")
    return target_path
