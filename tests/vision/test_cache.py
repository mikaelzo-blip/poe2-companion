"""Unit tests for ScreenshotCache TTL expiration and LRU size budget."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from companion.vision.cache import ScreenshotCache


def test_screenshot_cache_store_and_retrieve(tmp_path: Path) -> None:
    cache = ScreenshotCache(cache_dir=tmp_path, ttl_minutes=10, max_mb=10)
    data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

    path = cache.store("screen_1", data)
    assert path.exists()

    retrieved = cache.get("screen_1")
    assert retrieved == data

    # Non-existent
    assert cache.get("non_existent") is None


def test_screenshot_cache_ttl_expiration(tmp_path: Path) -> None:
    cache = ScreenshotCache(cache_dir=tmp_path, ttl_minutes=5, max_mb=10)
    t0 = datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)

    cache.store("old_screen", b"bytes", timestamp=t0)

    # 10 minutes later -> expired
    t1 = t0 + timedelta(minutes=10)
    assert cache.get("old_screen", now=t1) is None


def test_screenshot_cache_max_size_lru_pruning(tmp_path: Path) -> None:
    # 2 KB budget
    cache = ScreenshotCache(cache_dir=tmp_path, ttl_minutes=60, max_mb=1)
    # Mock max_bytes directly to 2000 bytes
    cache.max_bytes = 2000

    t0 = datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)
    cache.store("screen_a", b"A" * 1200, timestamp=t0)
    cache.store("screen_b", b"B" * 1200, timestamp=t0 + timedelta(seconds=1))

    # Storing screen_b (1200 bytes) + screen_a (1200 bytes) = 2400 > 2000
    # screen_a should be evicted
    assert cache.get("screen_a", now=t0 + timedelta(seconds=2)) is None
    assert cache.get("screen_b", now=t0 + timedelta(seconds=2)) == b"B" * 1200
