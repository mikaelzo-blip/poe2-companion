"""Deterministic session recap generator consuming journey history."""

from __future__ import annotations

from datetime import datetime
import json

from companion.recap.schema import SessionRecap
from companion.state.history import JourneyHistoryEntry


def generate_session_recap(
    entries: list[JourneyHistoryEntry], session_id: str | None = None
) -> SessionRecap:
    """Aggregate a sequence of journey history entries into a SessionRecap."""
    sess_id = session_id or "default_session"
    if not entries:
        return SessionRecap(session_id=sess_id)

    char_id: str | None = None
    zones: list[str] = []
    levels: list[int] = []
    deaths: int = 0
    timestamps: list[datetime] = []

    for entry in entries:
        if entry.character_id and char_id is None:
            char_id = entry.character_id

        try:
            ts = datetime.fromisoformat(entry.timestamp)
            timestamps.append(ts)
        except Exception:
            pass

        if entry.event_type in ("zone_transition", "zone_enter", "zone_generate"):
            z = entry.payload.get("zone")
            if z and z not in zones:
                zones.append(z)

        elif entry.event_type == "level_up":
            lvl = entry.payload.get("level")
            if isinstance(lvl, int):
                levels.append(lvl)

        elif entry.event_type == "death":
            deaths += 1

    start_iso: str | None = None
    end_iso: str | None = None
    duration_s = 0.0

    if timestamps:
        timestamps.sort()
        start_iso = timestamps[0].isoformat()
        end_iso = timestamps[-1].isoformat()
        duration_s = max(0.0, (timestamps[-1] - timestamps[0]).total_seconds())

    start_lvl: int | None = levels[0] if levels else None
    end_lvl: int | None = levels[-1] if levels else None
    gained = max(0, (end_lvl - start_lvl)) if (start_lvl is not None and end_lvl is not None) else 0

    return SessionRecap(
        session_id=sess_id,
        character_id=char_id,
        start_time=start_iso,
        end_time=end_iso,
        duration_seconds=duration_s,
        starting_level=start_lvl,
        ending_level=end_lvl,
        levels_gained=gained,
        zones_visited=zones,
        total_deaths=deaths,
        total_events=len(entries),
    )


def format_recap_text(recap: SessionRecap) -> str:
    """Format SessionRecap into a clean human-readable console report."""
    lines = [
        f"=== Session Recap [{recap.session_id}] ===",
        f"Character ID: {recap.character_id or 'Unknown'}",
        f"Duration: {recap.duration_seconds:.1f}s | Events Logged: {recap.total_events}",
    ]

    if recap.starting_level is not None and recap.ending_level is not None:
        lines.append(
            f"Levels Gained: {recap.levels_gained} ({recap.starting_level} -> {recap.ending_level})"
        )
    else:
        lines.append(f"Levels Gained: {recap.levels_gained}")

    lines.append(f"Deaths: {recap.total_deaths}")
    lines.append(f"Zones Visited ({len(recap.zones_visited)}):")
    for z in recap.zones_visited:
        lines.append(f"  - {z}")

    return "\n".join(lines)


def format_recap_json(recap: SessionRecap) -> str:
    """Format SessionRecap as indented JSON."""
    return json.dumps(recap.model_dump(), indent=2)
