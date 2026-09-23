"""Global boundary retention manager enforcing storage quotas."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from companion.observe.manifest import ManifestManager


class RetentionManager:
    """Manages global observation storage bounds at session boundaries."""

    DEFAULT_QUOTA_BYTES = 1_000_000_000  # 1 GB

    def __init__(
        self,
        base_dir: Path,
        quota_bytes: int = DEFAULT_QUOTA_BYTES,
        max_storage_bytes: int | None = None,
        max_sessions: int = 20,
    ) -> None:
        self.base_dir = base_dir
        self.quota_bytes = max_storage_bytes if max_storage_bytes is not None else quota_bytes
        self.max_sessions = max_sessions

    def _calc_dir_size(self, path: Path) -> int:
        """Calculate total bytes of all files in directory."""
        total = 0
        try:
            for item in path.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
        except Exception:
            pass
        return total

    def clean_storage(
        self,
        protected_session_ids: set[str] | None = None,
    ) -> list[str]:
        """Prune oldest unpinned, unprotected sessions until storage fits within quota."""
        if not self.base_dir.exists():
            return []

        protected = set(protected_session_ids or set())
        sessions: list[tuple[Path, int, str]] = []

        total_bytes = 0
        for entry in self.base_dir.iterdir():
            if not entry.is_dir():
                continue
            session_id = entry.name
            size = self._calc_dir_size(entry)
            total_bytes += size

            # Pinned sessions via .pinned file or explicit set
            is_pinned = (entry / ".pinned").exists() or session_id in protected
            if not is_pinned:
                # Get started_at from manifest if available, fallback to mtime
                started_at = ""
                manifest_path = entry / "session_manifest.json"
                if manifest_path.exists():
                    try:
                        m = ManifestManager(manifest_path).load()
                        if m:
                            started_at = m.started_at
                    except Exception:
                        pass
                if not started_at:
                    started_at = datetime.fromtimestamp(entry.stat().st_mtime, timezone.utc).isoformat()
                sessions.append((entry, size, started_at))

        if total_bytes <= self.quota_bytes:
            return []

        # Sort candidate sessions oldest first
        sessions.sort(key=lambda s: s[2])

        evicted: list[str] = []
        for path, size, _ in sessions:
            if total_bytes <= self.quota_bytes:
                break
            try:
                shutil.rmtree(path)
                total_bytes -= size
                evicted.append(path.name)
            except Exception:
                pass

        if evicted:
            self._log_evictions(evicted)

        return evicted

    def _log_evictions(self, evicted: list[str]) -> None:
        """Append eviction event to retention_log.jsonl."""
        log_path = self.base_dir / "retention_log.jsonl"
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "RETENTION_PRUNE",
            "evicted_sessions": evicted,
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
