"""Deterministic local live analysis data plane and factual signal generation."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from companion.observe.models import ObservationEnvelope
from companion.observe.privacy import PrivacyFilter
from companion.observe.reader import IncrementalStreamReader


def compute_local_signal_id(session_id: str, signal_type: str, source_event_ids: list[str]) -> str:
    """Compute deterministic local signal identity from structured inputs."""
    content = f"{session_id}:{signal_type}:{':'.join(sorted(source_event_ids))}"
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"sig:{session_id}:{signal_type}:{h}"


def read_bounded_client_log(
    client_log_path: Path,
    start_offset: int,
    max_bytes: int = 4096,
) -> str:
    """Read a strictly bounded byte window from Client.txt without full rescan, scrubbing sensitive chat."""
    if not client_log_path.exists():
        return ""
    start = max(0, start_offset)
    with open(client_log_path, "rb") as f:
        f.seek(start)
        chunk = f.read(max_bytes)

    text = chunk.decode("utf-8", errors="replace")
    sanitized_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if any(stripped.startswith(prefix) for prefix in ("@From", "@To", "#", "$", "%", "&", "!")):
            sanitized_lines.append("[REDACTED_CHAT]\n")
        elif "@From " in line or "@To " in line:
            sanitized_lines.append("[REDACTED_CHAT]\n")
        else:
            clean_line = re.sub(
                r"(?:password|secret|token|bearer|credential)\s*[:=]?\s*\S+",
                "[REDACTED_SECRET]",
                line,
                flags=re.IGNORECASE,
            )
            sanitized_lines.append(clean_line)
    return "".join(sanitized_lines)


class LocalSignal(BaseModel):
    """Factual, non-speculative observation signal emitted by local data plane."""

    model_config = ConfigDict(frozen=True)

    signal_id: str
    session_id: str
    signal_type: str
    severity: str = "INFO"  # INFO, WARN, HIGH, ERROR
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_event_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class LocalLiveAnalyst:
    """Deterministic local analysis engine running independently of AI reviewer."""

    def __init__(
        self,
        session_dir: Path,
        session_id: str,
        reader: IncrementalStreamReader | None = None,
    ) -> None:
        self.session_dir = session_dir
        self.session_id = session_id
        self.live_analysis_dir = self.session_dir / "live_analysis"
        self.live_analysis_dir.mkdir(parents=True, exist_ok=True)
        self.signals_path = self.live_analysis_dir / "local_signals.jsonl"

        self.reader = reader or IncrementalStreamReader(
            session_dir=self.session_dir,
            session_id=self.session_id,
        )

        self._persisted_signal_ids: set[str] = set()
        self._load_persisted_signal_ids()

        # In-memory tracking state
        self._objective_churn_count: dict[str, int] = {}
        self._unknown_field_counts: dict[str, int] = {}

    def _load_persisted_signal_ids(self) -> None:
        """Load already persisted signal IDs to ensure replay deduplication."""
        if not self.signals_path.exists():
            return
        try:
            with open(self.signals_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if "signal_id" in data:
                        self._persisted_signal_ids.add(data["signal_id"])
        except Exception:
            pass

    def _sanitize_details(self, details: dict[str, Any]) -> dict[str, Any]:
        """Strip whispers, credentials, tokens, and sensitive strings from signal details."""
        sanitized: dict[str, Any] = {}
        for k, v in details.items():
            if isinstance(v, str):
                # Redact whispers and chat markers
                if any(v.startswith(p) for p in ("@From", "@To", "#", "$", "%", "&", "!")):
                    sanitized[k] = "[REDACTED_CHAT]"
                elif re.search(r"(?:password|secret|token|bearer|credential)", v, re.IGNORECASE):
                    sanitized[k] = "[REDACTED_SECRET]"
                else:
                    sanitized[k] = v
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize_details(v)
            else:
                sanitized[k] = v
        return sanitized

    def step(self) -> list[LocalSignal]:
        """Execute one incremental analysis step."""
        envelopes = self.reader.read_new_envelopes()
        signals: list[LocalSignal] = []

        for env in envelopes:
            evt_id = env.event_id
            payload = env.payload or {}

            if env.event_type == "USER_MARKER":
                marker_id = payload.get("marker_id", "unknown")
                sig_id = compute_local_signal_id(self.session_id, "USER_MARKER_DETECTED", [evt_id])
                note = payload.get("note", "")
                details = self._sanitize_details({
                    "marker_id": marker_id,
                    "note": note,
                    "zone": payload.get("zone"),
                })
                signals.append(
                    LocalSignal(
                        signal_id=sig_id,
                        session_id=self.session_id,
                        signal_type="USER_MARKER_DETECTED",
                        severity="HIGH",
                        source_event_ids=[evt_id],
                        details=details,
                    )
                )

            elif env.event_type == "STATE_DELTA":
                status = payload.get("verification_status")
                field = payload.get("field")
                if status == "UNKNOWN" or payload.get("after") is None:
                    count = self._unknown_field_counts.get(str(field), 0) + 1
                    self._unknown_field_counts[str(field)] = count
                    sig_id = compute_local_signal_id(
                        self.session_id, f"UNKNOWN_PERSISTENCE_{field}", [evt_id]
                    )
                    signals.append(
                        LocalSignal(
                            signal_id=sig_id,
                            session_id=self.session_id,
                            signal_type="UNKNOWN_PERSISTENCE",
                            severity="WARN",
                            source_event_ids=[evt_id],
                            details={
                                "field": field,
                                "persistence_count": count,
                            },
                        )
                    )

            elif env.event_type == "OBJECTIVE_TRACE":
                changed = payload.get("objective_changed", False)
                obj_id = payload.get("selected_objective_id")
                if not changed and obj_id:
                    count = self._objective_churn_count.get(str(obj_id), 0) + 1
                    self._objective_churn_count[str(obj_id)] = count
                    sig_id = compute_local_signal_id(
                        self.session_id, f"OBJECTIVE_CHURN_{obj_id}", [evt_id]
                    )
                    signals.append(
                        LocalSignal(
                            signal_id=sig_id,
                            session_id=self.session_id,
                            signal_type="OBJECTIVE_CHURN",
                            severity="INFO",
                            source_event_ids=[evt_id],
                            details={
                                "objective_id": obj_id,
                                "reevaluation_count": count,
                            },
                        )
                    )

            elif env.event_type == "LOG_ANOMALY":
                pat_hash = payload.get("pattern_hash", "unknown")
                sig_id = compute_local_signal_id(
                    self.session_id, f"ANOMALY_REPETITION_{pat_hash}", [evt_id]
                )
                details = self._sanitize_details({
                    "pattern_hash": pat_hash,
                    "classification": payload.get("classification"),
                })
                signals.append(
                    LocalSignal(
                        signal_id=sig_id,
                        session_id=self.session_id,
                        signal_type="ANOMALY_REPETITION",
                        severity="WARN",
                        source_event_ids=[evt_id],
                        details=details,
                    )
                )

            elif env.event_type == "NOTIFICATION_TRACE":
                depth = payload.get("queue_depth", 0)
                if depth > 5:
                    sig_id = compute_local_signal_id(
                        self.session_id, "NOTIFICATION_QUEUE_SPIKE", [evt_id]
                    )
                    signals.append(
                        LocalSignal(
                            signal_id=sig_id,
                            session_id=self.session_id,
                            signal_type="NOTIFICATION_QUEUE_SPIKE",
                            severity="WARN",
                            source_event_ids=[evt_id],
                            details={"queue_depth": depth},
                        )
                    )

        # Order of operations:
        # 1. Read evidence (done above)
        # 2. Derive deterministic signals (done above)
        # 3. Durably persist derived signals to local_signals.jsonl (deduplicating by signal_id)
        new_signals_to_persist = [
            s for s in signals if s.signal_id not in self._persisted_signal_ids
        ]
        if new_signals_to_persist:
            with open(self.signals_path, "a", encoding="utf-8") as f:
                for s in new_signals_to_persist:
                    f.write(s.model_dump_json() + "\n")
                    self._persisted_signal_ids.add(s.signal_id)
                f.flush()
                os.fsync(f.fileno())

        # 4. ONLY after successful persistence, atomically advance reader cursor state
        self.reader.save_state()

        return signals
