"""File fingerprinting, stream identity classification, and checkpoint store."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from pydantic import BaseModel, ConfigDict

from companion.runtime.models import FileFingerprint, RuntimeCheckpoint


class FileIdentityClassification(str, Enum):
    """Classification of Client.txt file state relative to persisted checkpoint."""

    NORMAL_APPEND = "NORMAL_APPEND"
    TRUNCATION = "TRUNCATION"
    REPLACEMENT = "REPLACEMENT"
    MISSING = "MISSING"
    REAPPEARANCE = "REAPPEARANCE"
    AMBIGUOUS = "AMBIGUOUS"


class FileIdentityDecision(BaseModel):
    """Decision output from 6-case file identity engine."""

    model_config = ConfigDict(frozen=True)

    classification: FileIdentityClassification
    stream_epoch: int
    read_offset: int
    file_fingerprint: FileFingerprint | None = None
    reason: str


def generate_file_fingerprint(path: str | Path) -> FileFingerprint | None:
    """Generate lightweight file fingerprint for Client.txt using first 512 bytes + stat."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None

    try:
        st = p.stat()
        with open(p, "rb") as f:
            header_bytes = f.read(512)
        prefix_hash = hashlib.sha256(header_bytes).hexdigest()
        return FileFingerprint(
            path=str(p.resolve()),
            created_at=st.st_ctime,
            prefix_hash=prefix_hash,
            file_size_at_fingerprint=st.st_size,
        )
    except (OSError, PermissionError):
        return None


def classify_file_identity(
    current_path: str | Path,
    checkpoint: RuntimeCheckpoint | None,
    previous_state_missing: bool = False,
    default_start_to_eof: bool = False,
) -> FileIdentityDecision:
    """Classify current Client.txt file state against a saved checkpoint using the 6-case table."""
    p = Path(current_path)
    if not p.exists():
        # Case 4: Missing file
        last_epoch = checkpoint.stream_epoch if checkpoint else 1
        last_offset = checkpoint.last_offset if checkpoint else 0
        return FileIdentityDecision(
            classification=FileIdentityClassification.MISSING,
            stream_epoch=last_epoch,
            read_offset=last_offset,
            file_fingerprint=checkpoint.file_fingerprint if checkpoint else None,
            reason="Log file is missing or temporarily inaccessible",
        )

    current_fp = generate_file_fingerprint(p)
    if current_fp is None:
        # Case 6: Ambiguous / unreadable
        next_epoch = (checkpoint.stream_epoch + 1) if checkpoint else 1
        return FileIdentityDecision(
            classification=FileIdentityClassification.AMBIGUOUS,
            stream_epoch=next_epoch,
            read_offset=0,
            file_fingerprint=None,
            reason="Unable to generate file fingerprint for log file",
        )

    if checkpoint is None:
        # Initial run without checkpoint
        read_offset = current_fp.file_size_at_fingerprint if default_start_to_eof else 0
        return FileIdentityDecision(
            classification=FileIdentityClassification.NORMAL_APPEND,
            stream_epoch=1,
            read_offset=read_offset,
            file_fingerprint=current_fp,
            reason="Initial runtime baseline established",
        )

    prev_fp = checkpoint.file_fingerprint
    current_size = current_fp.file_size_at_fingerprint
    same_path = (str(p.resolve()) == prev_fp.path)
    same_prefix = (current_fp.prefix_hash == prev_fp.prefix_hash)
    # On Windows, st_ctime difference indicates new file creation
    same_ctime = abs(current_fp.created_at - prev_fp.created_at) < 0.001

    if checkpoint is not None and prev_fp.file_size_at_fingerprint >= 512 and current_size < 512:
        # Case 6: Partial initial bytes
        return FileIdentityDecision(
            classification=FileIdentityClassification.AMBIGUOUS,
            stream_epoch=checkpoint.stream_epoch + 1,
            read_offset=0,
            file_fingerprint=current_fp,
            reason="Log file has partial initial bytes (< 512 bytes); allocating new stream epoch",
        )

    if previous_state_missing:
        # Case 5: Reappearance
        if same_path and same_prefix and same_ctime:
            return FileIdentityDecision(
                classification=FileIdentityClassification.REAPPEARANCE,
                stream_epoch=checkpoint.stream_epoch,
                read_offset=checkpoint.last_offset,
                file_fingerprint=current_fp,
                reason="Log file reappeared with matching fingerprint",
            )
        else:
            return FileIdentityDecision(
                classification=FileIdentityClassification.REPLACEMENT,
                stream_epoch=checkpoint.stream_epoch + 1,
                read_offset=0,
                file_fingerprint=current_fp,
                reason="Log file reappeared with distinct fingerprint (replacement)",
            )

    if same_path and same_prefix and same_ctime:
        if current_size >= checkpoint.last_offset:
            # Case 1: Normal append
            return FileIdentityDecision(
                classification=FileIdentityClassification.NORMAL_APPEND,
                stream_epoch=checkpoint.stream_epoch,
                read_offset=checkpoint.last_offset,
                file_fingerprint=current_fp,
                reason="Log file appended normally; preserving stream epoch and offset",
            )
        else:
            # Case 2: In-place truncation
            return FileIdentityDecision(
                classification=FileIdentityClassification.TRUNCATION,
                stream_epoch=checkpoint.stream_epoch + 1,
                read_offset=0,
                file_fingerprint=current_fp,
                reason="Log file truncated in-place; allocating new stream epoch and resetting offset",
            )

    # Case 3: Replacement / rotation
    return FileIdentityDecision(
        classification=FileIdentityClassification.REPLACEMENT,
        stream_epoch=checkpoint.stream_epoch + 1,
        read_offset=0,
        file_fingerprint=current_fp,
        reason="Log file replaced or rotated; allocating new stream epoch",
    )


class RuntimeCheckpointStore:
    """Atomic load and save for session runtime checkpoints."""

    def __init__(self, checkpoint_path: str | Path) -> None:
        self.checkpoint_path = Path(checkpoint_path)

    def load(self) -> RuntimeCheckpoint | None:
        """Load and deserialize checkpoint from disk."""
        if not self.checkpoint_path.exists() or not self.checkpoint_path.is_file():
            return None
        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return RuntimeCheckpoint.model_validate(data)
        except Exception:
            return None

    def save(self, checkpoint: RuntimeCheckpoint) -> Path:
        """Atomically persist runtime checkpoint using temp file and atomic replace."""
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        dir_path = self.checkpoint_path.parent
        json_data = checkpoint.model_dump_json(indent=2)

        # Write to temporary file in same directory for atomic replace
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=dir_path,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            tmp.write(json_data)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_name = tmp.name

        try:
            os.replace(temp_name, self.checkpoint_path)
        except Exception:
            if os.path.exists(temp_name):
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
            raise
        return self.checkpoint_path

    def initialize_dirty_checkpoint(
        self,
        client_log_path: str | Path,
        existing_checkpoint: RuntimeCheckpoint | None = None,
        run_id: str | None = None,
        start_offset: int | None = None,
        stream_epoch: int | None = None,
    ) -> RuntimeCheckpoint:
        """Persist dirty-on-start checkpoint before consuming any live records."""
        current_run_id = run_id or uuid.uuid4().hex
        fp = generate_file_fingerprint(client_log_path)
        if fp is None:
            # Create synthetic initial fingerprint if file missing
            resolved = str(Path(client_log_path).resolve())
            fp = FileFingerprint(
                path=resolved,
                created_at=0.0,
                prefix_hash="",
                file_size_at_fingerprint=0,
            )

        epoch = stream_epoch if stream_epoch is not None else (
            existing_checkpoint.stream_epoch if existing_checkpoint else 1
        )
        offset = start_offset if start_offset is not None else (
            existing_checkpoint.last_offset if existing_checkpoint else 0
        )
        file_size = fp.file_size_at_fingerprint

        checkpoint = RuntimeCheckpoint(
            schema_version="1.0",
            file_fingerprint=fp,
            stream_epoch=epoch,
            last_offset=offset,
            last_file_size=file_size,
            updated_at=datetime.now(timezone.utc).isoformat(),
            clean_shutdown=False,
            clean_shutdown_at=None,
            run_id=current_run_id,
        )
        self.save(checkpoint)
        return checkpoint
