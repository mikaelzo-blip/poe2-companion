"""Unit tests for ClientLogTailer, rotation handling, and privacy filter."""

from __future__ import annotations

from pathlib import Path
import pytest

from companion.sensing.client_log import (
    ClientLogTailer,
    ParsedLogEvent,
    ParsedLogEventType,
    parse_log_line,
)


def test_parse_log_line_privacy_drop_chat() -> None:
    # Whispers
    assert parse_log_line("2026/09/22 10:00:00 123456 [INFO Client 1234] @From Player: hello") is None
    assert parse_log_line("2026/09/22 10:00:00 123456 [INFO Client 1234] @To Player: private msg") is None
    # Trade chat
    assert parse_log_line("2026/09/22 10:00:00 123456 [INFO Client 1234] $Player: WTS Divine 100c") is None
    # Global chat
    assert parse_log_line("2026/09/22 10:00:00 123456 [INFO Client 1234] #Player: general discussion") is None
    # Party chat
    assert parse_log_line("2026/09/22 10:00:00 123456 [INFO Client 1234] %Player: portal up") is None


def test_parse_log_line_recognized_events() -> None:
    # Zone enter
    line_zone = "2026/09/22 10:01:00 123456 [INFO Client 1234] : Entered area \"Clear Fell\""
    ev_zone = parse_log_line(line_zone)
    assert ev_zone is not None
    assert ev_zone.event_type == ParsedLogEventType.ZONE_ENTER
    assert ev_zone.payload.get("zone") == "Clear Fell"

    # Zone generate
    line_gen = "2026/09/22 10:00:30 123456 [INFO Client 1234] : Generating level 12 area \"The Crypt\""
    ev_gen = parse_log_line(line_gen)
    assert ev_gen is not None
    assert ev_gen.event_type == ParsedLogEventType.ZONE_GENERATE
    assert ev_gen.payload.get("zone") == "The Crypt"
    assert ev_gen.payload.get("area_level") == 12

    # Level up
    line_lvl = "2026/09/22 10:05:00 123456 [INFO Client 1234] : Mercenary_Exile is now level 52"
    ev_lvl = parse_log_line(line_lvl)
    assert ev_lvl is not None
    assert ev_lvl.event_type == ParsedLogEventType.LEVEL_UP
    assert ev_lvl.payload.get("character_name") == "Mercenary_Exile"
    assert ev_lvl.payload.get("level") == 52

    # Death
    line_death = "2026/09/22 10:10:00 123456 [INFO Client 1234] : Mercenary_Exile has been slain."
    ev_death = parse_log_line(line_death)
    assert ev_death is not None
    assert ev_death.event_type == ParsedLogEventType.DEATH
    assert ev_death.payload.get("character_name") == "Mercenary_Exile"


def test_tailer_partial_line_buffering(tmp_path: Path) -> None:
    log_file = tmp_path / "Client.txt"
    log_file.write_text("2026/09/22 10:00:00 123456 [INFO Client 1234] : Entered ", encoding="utf-8")

    tailer = ClientLogTailer(log_file)
    events = tailer.poll()
    # Incomplete line should not emit
    assert len(events) == 0

    # Append the rest of line + newline
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("area \"Omen Ridge\"\n")

    events = tailer.poll()
    assert len(events) == 1
    assert events[0].event_type == ParsedLogEventType.ZONE_ENTER
    assert events[0].payload.get("zone") == "Omen Ridge"


def test_tailer_rotation_handling(tmp_path: Path) -> None:
    log_file = tmp_path / "Client.txt"
    log_file.write_text(
        "2026/09/22 10:00:00 123456 [INFO Client 1234] : Entered area \"Town 1\"\n"
        "2026/09/22 10:01:00 123456 [INFO Client 1234] : Entered area \"Town 2\"\n",
        encoding="utf-8",
    )

    tailer = ClientLogTailer(log_file)
    evs1 = tailer.poll()
    assert len(evs1) == 2

    # File truncated / rotated: smaller file content
    log_file.write_text(
        "2026/09/22 10:05:00 123456 [INFO Client 1234] : Entered area \"New Map\"\n",
        encoding="utf-8",
    )

    evs2 = tailer.poll()
    assert len(evs2) == 1
    assert evs2[0].payload.get("zone") == "New Map"
