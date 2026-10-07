"""Unit tests for source archive unpacker and ZIP slip defense."""

import io
from pathlib import Path
import zipfile
import pytest

from companion.sources.unpacker import (
    EXPECTED_STAGES,
    ArchiveValidationError,
    ZipSlipError,
    match_logical_stage,
    unpack_source_archive,
    validate_archive_member_path,
)


def _create_mock_zip(files: dict[str, bytes]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    buf.seek(0)
    return buf


def test_match_logical_stage() -> None:
    assert match_logical_stage("lvl 1-14 - 0.5.5 Fubgun Flameblast Oil G.build") == "lvl 1-14"
    assert match_logical_stage("lvl 52 Swap - 0.5.5 Fubgun Flameblast Oi.build") == "lvl 52 Swap"
    assert match_logical_stage("DoT Cap - 0.5.5 Fubgun Flameblast Oil Gr.build") == "DoT Cap"
    assert match_logical_stage("unknown.build") is None


def test_zip_slip_traversal_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()

    with pytest.raises(ZipSlipError):
        validate_archive_member_path("../outside.build", target)

    with pytest.raises(ZipSlipError):
        validate_archive_member_path("sub/../../outside.build", target)


def test_zip_slip_absolute_paths_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()

    with pytest.raises(ZipSlipError):
        validate_archive_member_path("/etc/passwd", target)

    with pytest.raises(ZipSlipError):
        validate_archive_member_path("\\Windows\\System32", target)


def test_zip_slip_drive_qualified_paths_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()

    with pytest.raises(ZipSlipError):
        validate_archive_member_path("C:\\evil.build", target)

    with pytest.raises(ZipSlipError):
        validate_archive_member_path("D:/evil.build", target)


def test_synthetic_malicious_archive_aborts_without_extracting(tmp_path: Path) -> None:
    # Build a malicious archive with a traversal entry
    files = {
        "lvl 1-14 - 0.5.5 Fubgun Flameblast Oil G.build": b"{}",
        "../evil.build": b"pwned",
    }
    zip_bytes = _create_mock_zip(files).getvalue()
    zip_path = tmp_path / "malicious.zip"
    zip_path.write_bytes(zip_bytes)

    target_dir = tmp_path / "extracted"
    target_dir.mkdir()

    with pytest.raises(ZipSlipError):
        unpack_source_archive(zip_path, target_dir)

    # Assert no files were written to target_dir or parent
    assert list(target_dir.iterdir()) == []
    assert not (tmp_path / "evil.build").exists()


def test_missing_stages_raises_validation_error(tmp_path: Path) -> None:
    files = {
        "lvl 1-14 - 0.5.5 Fubgun Flameblast Oil G.build": b"{}",
    }
    zip_path = tmp_path / "incomplete.zip"
    zip_path.write_bytes(_create_mock_zip(files).getvalue())

    target_dir = tmp_path / "extracted"
    with pytest.raises(ArchiveValidationError) as exc:
        unpack_source_archive(zip_path, target_dir)
    assert "missing required progression stages" in str(exc.value)


def test_extraneous_file_raises_validation_error(tmp_path: Path) -> None:
    # All 9 valid plus 1 extra
    files = {
        f"{stage} - Fubgun.build": b"{}" for stage in EXPECTED_STAGES
    }
    files["unauthorized_script.py"] = b"print('hi')"
    zip_path = tmp_path / "extra.zip"
    zip_path.write_bytes(_create_mock_zip(files).getvalue())

    target_dir = tmp_path / "extracted"
    with pytest.raises(ArchiveValidationError) as exc:
        unpack_source_archive(zip_path, target_dir)
    assert "unexpected extraneous files" in str(exc.value)


def test_valid_unpacking_preserves_bytes(tmp_path: Path) -> None:
    content = b'{"name": "test", "author": "Fubgun"}'
    files = {
        f"{stage} - 0.5.5 Fubgun.build": content for stage in EXPECTED_STAGES
    }
    zip_path = tmp_path / "valid.zip"
    zip_path.write_bytes(_create_mock_zip(files).getvalue())

    target_dir = tmp_path / "extracted"
    snapshots = unpack_source_archive(zip_path, target_dir)

    assert len(snapshots) == 9
    for snap in snapshots:
        assert snap.target_path.is_file()
        assert snap.target_path.read_bytes() == content
        assert snap.byte_size == len(content)


def test_unpacking_custom_stages_accepts_non_fubgun_archive(tmp_path: Path) -> None:
    content = b'{"name": "Navira", "author": "MisoxShiru"}'
    files = {
        "Act 1 & 2 - Navira.build": content,
        "Act 2 - Navira.build": content,
        "Act 3 - Navira.build": content,
    }
    zip_path = tmp_path / "navira.zip"
    zip_path.write_bytes(_create_mock_zip(files).getvalue())

    target_dir = tmp_path / "extracted"
    custom_stages = ["Act 1 & 2", "Act 2", "Act 3"]
    snapshots = unpack_source_archive(zip_path, target_dir, expected_stages=custom_stages)

    assert len(snapshots) == 3
    stages_unpacked = [s.logical_stage for s in snapshots]
    assert stages_unpacked == custom_stages
    for snap in snapshots:
        assert snap.target_path.is_file()

