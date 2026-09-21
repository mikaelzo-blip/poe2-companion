"""Source archive unpacker with strict ZIP slip path traversal protection.

Extracts the nine expected pinned Fubgun 0.5.5 build snapshots from the supplied
source archive into immutable raw storage.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import zipfile

EXPECTED_STAGES: tuple[str, ...] = (
    "lvl 1-14",
    "lvl 15-32",
    "lvl 33-51",
    "lvl 52 Swap",
    "lvl 53-68",
    "lvl 85",
    "Endgame",
    "Mageblood",
    "DoT Cap",
)


class ZipSlipError(ValueError):
    """Raised when an archive entry contains a path traversal or unsafe target path."""
    pass


class ArchiveValidationError(ValueError):
    """Raised when the archive does not contain the expected build snapshots."""
    pass


@dataclass(frozen=True)
class UnpackedSnapshot:
    """Represents an unpacked snapshot file and its raw cryptographic digest."""
    logical_stage: str
    filename: str
    target_path: Path
    sha256: str
    byte_size: int


def match_logical_stage(filename: str) -> str | None:
    """Identify which of the nine progression stages matches the given filename."""
    clean_name = Path(filename).name.strip()
    for stage in EXPECTED_STAGES:
        if clean_name.startswith(stage):
            return stage
    return None


def validate_archive_member_path(member_name: str, target_dir: Path) -> Path:
    """Verify that an archive member path is strictly safe against ZIP slip traversal."""
    # Check for raw traversal sequences
    parts = member_name.replace("\\", "/").split("/")
    if ".." in parts:
        raise ZipSlipError(f"Prohibited traversal '..' detected in entry '{member_name}'")

    # Check for absolute path or Windows drive-qualified path
    if member_name.startswith(("/", "\\")):
        raise ZipSlipError(f"Prohibited absolute path in entry '{member_name}'")

    # Check for Windows drive letters (e.g. C:, D:)
    if len(member_name) > 1 and member_name[1] == ":":
        raise ZipSlipError(f"Prohibited drive-qualified path in entry '{member_name}'")

    target_resolved = target_dir.resolve()
    dest_path = (target_resolved / member_name).resolve()

    # Ensure resolved path is strictly within target directory
    try:
        common = os.path.commonpath([str(target_resolved), str(dest_path)])
    except ValueError:
        raise ZipSlipError(f"Entry '{member_name}' escapes target directory '{target_resolved}'")

    if common != str(target_resolved):
        raise ZipSlipError(f"Entry '{member_name}' escapes target directory '{target_resolved}'")

    return dest_path


def unpack_source_archive(
    archive_path: str | Path,
    target_dir: str | Path,
) -> list[UnpackedSnapshot]:
    """Unpack all expected .build snapshots from archive into target_dir with ZIP slip protection.
    
    Raw source bytes are written exactly as extracted without modification.
    SHA-256 is computed directly on the extracted bytes.
    """
    archive_file = Path(archive_path)
    target_path = Path(target_dir)

    if not archive_file.is_file():
        raise FileNotFoundError(f"Source archive not found: {archive_file}")

    target_path.mkdir(parents=True, exist_ok=True)

    unpacked: list[UnpackedSnapshot] = []
    found_stages: dict[str, str] = {}
    extraneous_files: list[str] = []

    with zipfile.ZipFile(archive_file, "r") as zf:
        # Phase 1: Pre-validate all members before extracting anything
        for info in zf.infolist():
            if info.is_dir():
                continue

            # Validate ZIP slip protection
            dest_file = validate_archive_member_path(info.filename, target_path)

            filename = Path(info.filename).name
            if not filename.endswith(".build"):
                extraneous_files.append(info.filename)
                continue

            stage = match_logical_stage(filename)
            if not stage:
                extraneous_files.append(info.filename)
            else:
                found_stages[stage] = filename

        # Validate completeness of expected 9 stages
        missing_stages = [s for s in EXPECTED_STAGES if s not in found_stages]
        if missing_stages:
            raise ArchiveValidationError(
                f"Archive is missing required progression stages: {missing_stages}"
            )
        if extraneous_files:
            raise ArchiveValidationError(
                f"Archive contains unexpected extraneous files: {extraneous_files}"
            )

        # Phase 2: Extract verified entries in stage order
        for stage in EXPECTED_STAGES:
            member_filename = found_stages[stage]
            raw_bytes = zf.read(member_filename)
            digest = hashlib.sha256(raw_bytes).hexdigest()
            byte_size = len(raw_bytes)

            dest_path = target_path / Path(member_filename).name
            dest_path.write_bytes(raw_bytes)

            unpacked.append(
                UnpackedSnapshot(
                    logical_stage=stage,
                    filename=dest_path.name,
                    target_path=dest_path,
                    sha256=digest,
                    byte_size=byte_size,
                )
            )

    return unpacked
