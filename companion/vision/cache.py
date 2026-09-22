"""Local screenshot cache with time-to-live expiration and LRU size budgeting."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


class ScreenshotCache:
    """Manages screenshot file artifacts on disk with TTL and storage ceilings."""

    def __init__(
        self,
        cache_dir: Path | str,
        ttl_minutes: int = 30,
        max_mb: int = 500,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_minutes = ttl_minutes
        self.max_bytes = max_mb * 1024 * 1024
        # Mapping: image_id -> {"path": Path, "size": int, "created_at": float, "last_accessed": float}
        self._entries: dict[str, dict[str, float | Path | int]] = {}

    def store(
        self,
        image_id: str,
        data: bytes,
        timestamp: datetime | None = None,
    ) -> Path:
        """Store screenshot data and enforce cache constraints."""
        ts = timestamp or datetime.now(timezone.utc)
        file_path = self.cache_dir / f"{image_id}.png"
        file_path.write_bytes(data)

        self._entries[image_id] = {
            "path": file_path,
            "size": len(data),
            "created_at": ts.timestamp(),
            "last_accessed": ts.timestamp(),
        }

        self.cleanup(now=ts)
        return file_path

    def get(self, image_id: str, now: datetime | None = None) -> bytes | None:
        """Retrieve screenshot data if not expired."""
        if image_id not in self._entries:
            return None

        current_time = now or datetime.now(timezone.utc)
        entry = self._entries[image_id]
        created_at = float(entry["created_at"])
        ttl_seconds = self.ttl_minutes * 60

        if (current_time.timestamp() - created_at) > ttl_seconds:
            self._evict(image_id)
            return None

        entry["last_accessed"] = current_time.timestamp()
        target_path = Path(entry["path"])
        if target_path.exists():
            return target_path.read_bytes()
        return None

    def cleanup(self, now: datetime | None = None) -> int:
        """Evict expired items and items exceeding max_bytes (LRU order)."""
        current_time = now or datetime.now(timezone.utc)
        evicted = 0
        ttl_seconds = self.ttl_minutes * 60

        # 1. Evict expired
        to_remove = [
            img_id
            for img_id, entry in self._entries.items()
            if (current_time.timestamp() - float(entry["created_at"])) > ttl_seconds
        ]
        for img_id in to_remove:
            self._evict(img_id)
            evicted += 1

        # 2. Evict least recently accessed if over size budget
        total_size = sum(int(e["size"]) for e in self._entries.values())
        if total_size > self.max_bytes:
            # Sort by last_accessed ascending (oldest access first)
            sorted_entries = sorted(
                self._entries.items(),
                key=lambda item: float(item[1]["last_accessed"]),
            )
            for img_id, entry in sorted_entries:
                if total_size <= self.max_bytes:
                    break
                size = int(entry["size"])
                self._evict(img_id)
                total_size -= size
                evicted += 1

        return evicted

    def _evict(self, image_id: str) -> None:
        """Remove entry from tracking and delete from disk."""
        entry = self._entries.pop(image_id, None)
        if entry:
            p = Path(entry["path"])
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

    @property
    def total_size_bytes(self) -> int:
        return sum(int(e["size"]) for e in self._entries.values())
