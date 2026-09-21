"""Staleness evaluation for provenanced character observations."""

from __future__ import annotations

from datetime import datetime, timezone


def is_observation_stale(
    timestamp_iso: str | None,
    max_age_seconds: int = 3600,
    current_time: datetime | None = None,
) -> bool:
    """Check if an ISO timestamp is older than max_age_seconds."""
    if not timestamp_iso:
        return True

    try:
        ts = datetime.fromisoformat(timestamp_iso)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return True

    now = current_time or datetime.now(timezone.utc)
    diff = (now - ts).total_seconds()
    return diff > max_age_seconds
