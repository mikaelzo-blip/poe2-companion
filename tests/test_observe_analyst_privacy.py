"""Tests for privacy redaction and bounded raw reading in companion.observe.analyst."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from companion.observe.analyst import (
    LocalLiveAnalyst,
    read_bounded_client_log,
)
from companion.observe.models import (
    EvidencePriority,
    FactKind,
    ObservationEnvelope,
)


def _make_env(session_id: str, seq: int, event_type: str, payload: dict) -> ObservationEnvelope:
    return ObservationEnvelope(
        observation_session_id=session_id,
        sequence_number=seq,
        taxonomy=FactKind.OBSERVED_FACT,
        event_type=event_type,
        priority=EvidencePriority.MEDIUM,
        payload=payload,
    )


def test_privacy_whispers_and_credentials_scrubbed_from_signals(tmp_path: Path) -> None:
    session_id = "obs_priv_test"
    sdir = tmp_path / session_id
    sdir.mkdir(parents=True)

    events_file = sdir / "events.jsonl"
    env1 = _make_env(
        session_id,
        1,
        "LOG_ANOMALY",
        {
            "line": "@From SensitivePlayer: my secret token is Bearer eyJhbGciOi...",
            "pattern_hash": "pat_1",
            "classification": "UNKNOWN",
        },
    )
    events_file.write_text(env1.model_dump_json() + "\n", encoding="utf-8")

    analyst = LocalLiveAnalyst(session_dir=sdir, session_id=session_id)
    signals = analyst.step()

    signals_file = sdir / "live_analysis" / "local_signals.jsonl"
    content = signals_file.read_text(encoding="utf-8")

    assert "SensitivePlayer" not in content
    assert "Bearer eyJ" not in content
    assert "secret token" not in content


def test_bounded_client_log_read_without_full_rescan(tmp_path: Path) -> None:
    client_log = tmp_path / "Client.txt"
    # Create large dummy log (100 KB) using explicit binary write
    filler = b"2026/09/23 14:00:00 [DEBUG] Routine engine tick\n" * 2000
    sensitive_whisper = b"2026/09/23 14:05:00 @From Alice: confidential chat message\n"
    target_line = b"2026/09/23 14:05:01 [ENGINE] Target event at specific offset\n"

    part1 = filler[:50000]
    full_bytes = part1 + sensitive_whisper + target_line + filler[50000:]
    with open(client_log, "wb") as f:
        f.write(full_bytes)

    log_size = client_log.stat().st_size
    assert log_size > 50000

    target_offset = len(part1) + len(sensitive_whisper)
    # Read bounded window of 200 bytes around target_offset
    read_text = read_bounded_client_log(
        client_log_path=client_log,
        start_offset=target_offset,
        max_bytes=200,
    )

    assert "Target event at specific offset" in read_text
    # Confidential chat is outside target window or scrubbed
    assert "confidential chat message" not in read_text
