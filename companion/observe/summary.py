"""Session summary aggregation and review candidate identification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from companion.observe.manifest import ManifestManager, SessionManifest


class SessionSummaryGenerator:
    """Generates structured summary metrics and review candidates for an observation session."""

    def __init__(self, session_dir: Path) -> None:
        self.session_dir = session_dir

    def _read_jsonl(self, filename: str) -> list[dict[str, Any]]:
        stem = filename.removesuffix(".jsonl")
        paths = [self.session_dir / filename]
        paths.extend(
            sorted(
                (p for p in self.session_dir.glob(f"{stem}.*.jsonl")
                 if p.name.removeprefix(f"{stem}.").removesuffix(".jsonl").isdigit()),
                key=lambda p: int(p.name.removeprefix(f"{stem}.").removesuffix(".jsonl")),
            )
        )
        items = []
        for path in paths:
            if not path.exists():
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            items.append(json.loads(line))
                        except Exception:
                            pass
        return items

    def _read_json(self, filename: str) -> dict[str, Any]:
        path = self.session_dir / filename
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def generate(self, manifest: SessionManifest | None = None) -> dict[str, Any]:
        if manifest is None:
            manifest_file = self.session_dir / "session_manifest.json"
            if manifest_file.exists():
                manifest = ManifestManager(manifest_file).load()
        manifest_data = manifest.model_dump(mode="json") if manifest else {}

        session_id = manifest_data.get("session_id", self.session_dir.name)
        status = manifest_data.get("status", "UNKNOWN")

        events = self._read_jsonl("events.jsonl")
        state_deltas = self._read_jsonl("state_deltas.jsonl")
        objective_traces = self._read_jsonl("objective_traces.jsonl")
        notification_traces = self._read_jsonl("notification_traces.jsonl")
        telemetry = self._read_jsonl("telemetry.jsonl")
        markers = self._read_jsonl("markers.jsonl")
        anomalies = self._read_json("anomalies.json")

        screenshots_dir = self.session_dir / "screenshots"
        screenshot_files = list(screenshots_dir.glob("*.png")) if screenshots_dir.exists() else []

        counts = {
            "events": len(events),
            "state_deltas": len(state_deltas),
            "objective_evaluations": len(objective_traces),
            "notifications": len(notification_traces),
            "markers": len(markers),
            "anomalies": len(anomalies),
            "screenshots": len(screenshot_files),
        }

        # Candidate reviews
        candidates = []
        for sig, anom in anomalies.items():
            if isinstance(anom, dict) and anom.get("occurrence_count", 0) > 1:
                candidates.append({
                    "category": "PARSER_GAP_CANDIDATE",
                    "signature": sig,
                    "details": "Sample withheld",
                    "count": anom.get("occurrence_count", 0),
                })

        summary = {
            "session_id": session_id,
            "runtime_run_id": manifest_data.get("runtime_run_id", ""),
            "started_at": manifest_data.get("started_at"),
            "ended_at": manifest_data.get("ended_at"),
            "status": status,
            "counts": counts,
            "manifest": manifest_data,
            "candidates": candidates,
        }

        # Write session_summary.json
        summary_json = self.session_dir / "session_summary.json"
        summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        # Write session_summary.md
        summary_md = self.session_dir / "session_summary.md"
        md_text = f"""# Observation Session Summary: {session_id}

- **Status**: {status}
- **Started**: {manifest_data.get("started_at")}
- **Ended**: {manifest_data.get("ended_at")}
- **Events Persisted**: {manifest_data.get("persisted_event_count", counts["events"])}
- **Events Dropped**: {manifest_data.get("dropped_event_count", 0)}

## Stream Counts
- State Deltas: {counts['state_deltas']}
- Objective Evaluations: {counts['objective_evaluations']}
- Notifications: {counts['notifications']}
- Manual Markers: {counts['markers']}
- Anomalies Detected: {counts['anomalies']}
- Screenshots Captured: {counts['screenshots']}

## Review Candidates
"""
        if candidates:
            for c in candidates:
                md_text += f"- **[{c['category']}]** {c['details']} (Occurrences: {c['count']})\n"
        else:
            md_text += "- None identified\n"

        summary_md.write_text(md_text, encoding="utf-8")
        return summary
