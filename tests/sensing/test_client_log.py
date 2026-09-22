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

    # Zone enter with bracket prefix
    line_zone_bracket = "2026/09/22 10:01:00 123456 [DEBUG Client 1234] Entered area \"Clear Fell\""
    ev_zone_bracket = parse_log_line(line_zone_bracket)
    assert ev_zone_bracket is not None
    assert ev_zone_bracket.event_type == ParsedLogEventType.ZONE_ENTER
    assert ev_zone_bracket.payload.get("zone") == "Clear Fell"


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


def test_tailer_backlog_large_file_sequential_polls(tmp_path: Path) -> None:
    log_file = tmp_path / "Client.txt"
    total_records = 2500
    with open(log_file, "wb") as f:
        for i in range(1, total_records + 1):
            f.write(f"2026/09/22 10:00:00 123456 [INFO Client 1234] : Player_{i} is now level {i}\n".encode("utf-8"))

    tailer = ClientLogTailer(log_file)

    # Poll 1: exactly 1000 lines
    evs1 = tailer.poll(max_lines=1000)
    assert len(evs1) == 1000
    assert evs1[0].payload["level"] == 1
    assert evs1[-1].payload["level"] == 1000

    # Poll 2: next 1000 lines (lines 1001-2000)
    evs2 = tailer.poll(max_lines=1000)
    assert len(evs2) == 1000
    assert evs2[0].payload["level"] == 1001
    assert evs2[-1].payload["level"] == 2000

    # Poll 3: remaining 500 lines (lines 2001-2500)
    evs3 = tailer.poll(max_lines=1000)
    assert len(evs3) == 500
    assert evs3[0].payload["level"] == 2001
    assert evs3[-1].payload["level"] == 2500

    # Poll 4: nothing left
    evs4 = tailer.poll(max_lines=1000)
    assert len(evs4) == 0

    all_levels = [e.payload["level"] for e in (evs1 + evs2 + evs3)]
    assert all_levels == list(range(1, total_records + 1))


def test_tailer_binary_decoding_and_malformed_bytes(tmp_path: Path) -> None:
    log_file = tmp_path / "Client.txt"
    with open(log_file, "wb") as f:
        # Non-ASCII UTF-8
        f.write("2026/09/22 10:00:00 123456 [INFO Client 1234] : Jörn_Exile is now level 10\n".encode("utf-8"))
        # Corrupted / invalid UTF-8 byte sequence
        f.write(b"2026/09/22 10:01:00 123456 [INFO Client 1234] : \xff\xfe\x80 Corrupted Bytes\n")
        # Valid subsequent line
        f.write(b"2026/09/22 10:02:00 123456 [INFO Client 1234] : Entered area \"Clear Fell\"\n")

    tailer = ClientLogTailer(log_file)
    events = tailer.poll(max_lines=100)

    # 1st event is valid non-ASCII level up
    assert len(events) == 2
    assert events[0].event_type == ParsedLogEventType.LEVEL_UP
    assert events[0].payload["character_name"] == "Jörn_Exile"
    assert events[0].payload["level"] == 10

    # 2nd event is the subsequent valid line (corrupted line safely discarded without crash/offset issue)
    assert events[1].event_type == ParsedLogEventType.ZONE_ENTER
    assert events[1].payload["zone"] == "Clear Fell"


def test_tailer_partial_trailing_byte_line_across_growth(tmp_path: Path) -> None:
    log_file = tmp_path / "Client.txt"
    # Write complete line 1, incomplete line 2
    with open(log_file, "wb") as f:
        f.write(b"2026/09/22 10:00:00 123456 [INFO Client 1234] : Entered area \"Town 1\"\n")
        f.write(b"2026/09/22 10:01:00 123456 [INFO Client 1234] : Entered area \"Incomp")

    tailer = ClientLogTailer(log_file)
    evs1 = tailer.poll()
    assert len(evs1) == 1
    assert evs1[0].payload["zone"] == "Town 1"

    # Complete line 2 and add line 3
    with open(log_file, "ab") as f:
        f.write(b"lete Town\"\n")
        f.write(b"2026/09/22 10:02:00 123456 [INFO Client 1234] : Entered area \"Town 3\"\n")

    evs2 = tailer.poll()
    assert len(evs2) == 2
    assert evs2[0].payload["zone"] == "Incomplete Town"
    assert evs2[1].payload["zone"] == "Town 3"


def test_parse_poe2_level_up_with_class_token() -> None:
    # Real PoE2 format with parenthetical class token
    line_poe2 = "2026/09/22 10:00:00 123456 [INFO Client 1234] : BOMSHAK (Mercenary) is now level 11"
    ev_poe2 = parse_log_line(line_poe2)
    assert ev_poe2 is not None
    assert ev_poe2.event_type == ParsedLogEventType.LEVEL_UP
    assert ev_poe2.payload["character_name"] == "BOMSHAK"
    assert ev_poe2.payload.get("character_class") == "Mercenary"
    assert ev_poe2.payload["level"] == 11

    # Legacy format without class token
    line_legacy = "2026/09/22 10:00:00 123456 [INFO Client 1234] : Mercenary_Exile is now level 52"
    ev_legacy = parse_log_line(line_legacy)
    assert ev_legacy is not None
    assert ev_legacy.event_type == ParsedLogEventType.LEVEL_UP
    assert ev_legacy.payload["character_name"] == "Mercenary_Exile"
    assert "character_class" not in ev_legacy.payload
    assert ev_legacy.payload["level"] == 52

    # Chat line disguised as level-up must be rejected
    line_chat = "2026/09/22 10:00:00 123456 [INFO Client 1234] @From Player: BOMSHAK (Mercenary) is now level 11"
    assert parse_log_line(line_chat) is None


def test_parse_poe2_real_zone_generate_without_colon() -> None:
    # Real observed PoE2 line without colon after [DEBUG Client <pid>]
    line_real = (
        '2026/09/23 02:41:59 58968640 2caa229f [DEBUG Client 18772] '
        'Generating level 10 area "G1_11" with seed 2336047553'
    )
    ev = parse_log_line(line_real)
    assert ev is not None
    assert ev.event_type == ParsedLogEventType.ZONE_GENERATE
    assert ev.payload["zone"] == "G1_11"
    assert ev.payload["area_level"] == 10

    # Retain test for legacy colon form
    line_legacy = '2026/09/22 10:00:30 123456 [INFO Client 1234] : Generating level 12 area "The Crypt"'
    ev_legacy = parse_log_line(line_legacy)
    assert ev_legacy is not None
    assert ev_legacy.event_type == ParsedLogEventType.ZONE_GENERATE
    assert ev_legacy.payload["zone"] == "The Crypt"
    assert ev_legacy.payload["area_level"] == 12


def test_parse_log_line_negative_and_anti_overmatch() -> None:
    # 1. Chat containing "Generating level" must be dropped by chat filter
    chat_whisper = '2026/09/23 02:41:59 123456 [INFO Client 1234] @From Friend: Generating level 10 area "G1_11"'
    assert parse_log_line(chat_whisper) is None

    chat_global = '2026/09/23 02:41:59 123456 [INFO Client 1234] #Player: Generating level 10 area "G1_11"'
    assert parse_log_line(chat_global) is None

    chat_trade = '2026/09/23 02:41:59 123456 [INFO Client 1234] $Trader: Generating level 10 area "G1_11"'
    assert parse_log_line(chat_trade) is None

    # 2. Arbitrary text containing "Entered area"
    chat_entered = '2026/09/23 02:41:59 123456 [INFO Client 1234] #Player: I just Entered area "Town"'
    assert parse_log_line(chat_entered) is None

    arbitrary_text = '2026/09/23 02:41:59 123456 Random system notice Entered area "Secret"'
    assert parse_log_line(arbitrary_text) is None

    # 3. Malformed area lines
    malformed_level = '2026/09/23 02:41:59 123456 [DEBUG Client 18772] Generating level notanumber area "G1_11"'
    assert parse_log_line(malformed_level) is None

    malformed_unquoted_zone = '2026/09/23 02:41:59 123456 [DEBUG Client 18772] Generating level 10 area G1_11'
    assert parse_log_line(malformed_unquoted_zone) is None

    malformed_unquoted_enter = '2026/09/23 02:41:59 123456 [DEBUG Client 18772] Entered area Unquoted'
    assert parse_log_line(malformed_unquoted_enter) is None

    # 4. Unrelated DEBUG lines
    debug_asset = '2026/09/23 02:41:59 123456 [DEBUG Client 18772] Async loading asset "art/textures/environment.dds"'
    assert parse_log_line(debug_asset) is None

    debug_device = '2026/09/23 02:41:59 123456 [DEBUG Client 18772] Direct3D12 device created successfully'
    assert parse_log_line(debug_device) is None

    debug_connect = '2026/09/23 02:41:59 123456 [DEBUG Client 18772] Connect to instance server 127.0.0.1:1234'
    assert parse_log_line(debug_connect) is None
