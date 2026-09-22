"""Unit tests for file fingerprinting, identity classification, and checkpoint store."""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from companion.runtime.checkpoint import (
    FileIdentityClassification,
    RuntimeCheckpointStore,
    classify_file_identity,
    generate_file_fingerprint,
)
from companion.runtime.models import FileFingerprint, RuntimeCheckpoint


@pytest.fixture
def temp_runtime_dir(tmp_path: Path) -> Path:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


@pytest.fixture
def mock_log_file(tmp_path: Path) -> Path:
    log_file = tmp_path / "Client.txt"
    log_file.write_bytes(b"Header line 1\nHeader line 2\n" + b"x" * 600)
    return log_file


def test_generate_file_fingerprint(mock_log_file: Path) -> None:
    fp = generate_file_fingerprint(mock_log_file)
    assert fp is not None
    assert Path(fp.path) == mock_log_file.resolve()
    assert len(fp.prefix_hash) == 64
    assert fp.file_size_at_fingerprint == mock_log_file.stat().st_size
    assert fp.created_at > 0


def test_generate_file_fingerprint_missing_file(tmp_path: Path) -> None:
    non_existent = tmp_path / "does_not_exist.txt"
    assert generate_file_fingerprint(non_existent) is None


def test_classify_normal_append(mock_log_file: Path) -> None:
    fp = generate_file_fingerprint(mock_log_file)
    assert fp is not None
    cp = RuntimeCheckpoint(
        file_fingerprint=fp,
        stream_epoch=1,
        last_offset=200,
        last_file_size=mock_log_file.stat().st_size,
        updated_at="2026-09-23T12:00:00Z",
        clean_shutdown=True,
    )
    # Append some bytes
    with open(mock_log_file, "ab") as f:
        f.write(b"new log line\n")

    decision = classify_file_identity(mock_log_file, cp)
    assert decision.classification == FileIdentityClassification.NORMAL_APPEND
    assert decision.stream_epoch == 1
    assert decision.read_offset == 200


def test_classify_truncation(mock_log_file: Path) -> None:
    fp = generate_file_fingerprint(mock_log_file)
    assert fp is not None
    cp = RuntimeCheckpoint(
        file_fingerprint=fp,
        stream_epoch=1,
        last_offset=620,
        last_file_size=mock_log_file.stat().st_size,
        updated_at="2026-09-23T12:00:00Z",
        clean_shutdown=True,
    )
    # Truncate file so size < last_offset, but first 512 bytes intact
    mock_log_file.write_bytes(mock_log_file.read_bytes()[:550])

    decision = classify_file_identity(mock_log_file, cp)
    assert decision.classification == FileIdentityClassification.TRUNCATION
    assert decision.stream_epoch == 2
    assert decision.read_offset == 0


def test_classify_ambiguous_partial_header(mock_log_file: Path) -> None:
    fp = generate_file_fingerprint(mock_log_file)
    assert fp is not None
    cp = RuntimeCheckpoint(
        file_fingerprint=fp,
        stream_epoch=1,
        last_offset=400,
        last_file_size=mock_log_file.stat().st_size,
        updated_at="2026-09-23T12:00:00Z",
        clean_shutdown=True,
    )
    # Truncate file to less than 512 bytes
    mock_log_file.write_bytes(b"short partial bytes")

    decision = classify_file_identity(mock_log_file, cp)
    assert decision.classification in (
        FileIdentityClassification.AMBIGUOUS,
        FileIdentityClassification.TRUNCATION,
        FileIdentityClassification.REPLACEMENT,
    )



def test_classify_replacement(mock_log_file: Path, tmp_path: Path) -> None:
    fp = generate_file_fingerprint(mock_log_file)
    assert fp is not None
    cp = RuntimeCheckpoint(
        file_fingerprint=fp,
        stream_epoch=1,
        last_offset=200,
        last_file_size=mock_log_file.stat().st_size,
        updated_at="2026-09-23T12:00:00Z",
        clean_shutdown=True,
    )
    # Replace file with different header content
    mock_log_file.unlink()
    mock_log_file.write_bytes(b"Different header\n" + b"y" * 600)

    decision = classify_file_identity(mock_log_file, cp)
    assert decision.classification == FileIdentityClassification.REPLACEMENT
    assert decision.stream_epoch == 2
    assert decision.read_offset == 0


def test_classify_missing_file(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.txt"
    fp = FileFingerprint(
        path=str(missing_file.resolve()),
        created_at=1700000000.0,
        prefix_hash="a" * 64,
        file_size_at_fingerprint=1000,
    )
    cp = RuntimeCheckpoint(
        file_fingerprint=fp,
        stream_epoch=1,
        last_offset=200,
        last_file_size=1000,
        updated_at="2026-09-23T12:00:00Z",
        clean_shutdown=True,
    )

    decision = classify_file_identity(missing_file, cp)
    assert decision.classification == FileIdentityClassification.MISSING
    assert decision.stream_epoch == 1
    assert decision.read_offset == 200


def test_classify_reappearance_matching(mock_log_file: Path) -> None:
    fp = generate_file_fingerprint(mock_log_file)
    assert fp is not None
    cp = RuntimeCheckpoint(
        file_fingerprint=fp,
        stream_epoch=1,
        last_offset=200,
        last_file_size=mock_log_file.stat().st_size,
        updated_at="2026-09-23T12:00:00Z",
        clean_shutdown=True,
    )

    decision = classify_file_identity(mock_log_file, cp, previous_state_missing=True)
    assert decision.classification == FileIdentityClassification.REAPPEARANCE
    assert decision.stream_epoch == 1
    assert decision.read_offset == 200


def test_checkpoint_store_atomic_save_and_load(temp_runtime_dir: Path, mock_log_file: Path) -> None:
    store = RuntimeCheckpointStore(temp_runtime_dir / "session_checkpoint.json")
    assert store.load() is None

    fp = generate_file_fingerprint(mock_log_file)
    assert fp is not None
    cp = RuntimeCheckpoint(
        file_fingerprint=fp,
        stream_epoch=1,
        last_offset=123,
        last_file_size=mock_log_file.stat().st_size,
        updated_at="2026-09-23T12:00:00Z",
        clean_shutdown=False,
        run_id="test-run-123",
    )

    saved_path = store.save(cp)
    assert saved_path.exists()

    loaded = store.load()
    assert loaded is not None
    assert loaded.stream_epoch == 1
    assert loaded.last_offset == 123
    assert loaded.clean_shutdown is False
    assert loaded.run_id == "test-run-123"


def test_checkpoint_dirty_on_start(temp_runtime_dir: Path, mock_log_file: Path) -> None:
    store = RuntimeCheckpointStore(temp_runtime_dir / "session_checkpoint.json")
    fp = generate_file_fingerprint(mock_log_file)
    assert fp is not None

    clean_cp = RuntimeCheckpoint(
        file_fingerprint=fp,
        stream_epoch=1,
        last_offset=123,
        last_file_size=mock_log_file.stat().st_size,
        updated_at="2026-09-23T12:00:00Z",
        clean_shutdown=True,
        clean_shutdown_at="2026-09-23T12:00:00Z",
        run_id="old-run",
    )
    store.save(clean_cp)

    dirty_cp = store.initialize_dirty_checkpoint(
        client_log_path=mock_log_file,
        existing_checkpoint=clean_cp,
        run_id="new-run-999",
    )
    assert dirty_cp.clean_shutdown is False
    assert dirty_cp.clean_shutdown_at is None
    assert dirty_cp.run_id == "new-run-999"

    # Verify persisted to disk immediately
    reloaded = store.load()
    assert reloaded is not None
    assert reloaded.clean_shutdown is False
    assert reloaded.run_id == "new-run-999"
