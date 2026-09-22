"""Sanitized real-log regression test suite validating PoE2 level-ups, batch tailing, and privacy filtering."""

from __future__ import annotations

from pathlib import Path
import pytest

from companion.sensing.client_log import (
    ClientLogTailer,
    ParsedLogEvent,
    ParsedLogEventType,
    parse_log_line,
)


def _generate_synthetic_poe2_log_stream() -> list[str]:
    """Generate synthetic log stream modeling 49 level-up events, interspersed chat, and area transitions."""
    lines: list[str] = []
    ts_base = "2026/09/22 10:"

    classes = ["Mercenary", "Warrior", "Sorceress", "Monk", "Ranger", "Witch"]

    # Act 1 start
    lines.append(f"{ts_base}00:01 123456 [INFO Client 1234] : Entered area \"Clear Fell\"")
    lines.append(f"{ts_base}00:02 123456 [INFO Client 1234] @From TraderBob: hi want to buy 1 divine for 100c?")
    lines.append(f"{ts_base}00:03 123456 [INFO Client 1234] $SpamBot: WTS fast carry cheap")

    level_event_count = 49
    for i in range(1, level_event_count + 1):
        cls = classes[i % len(classes)]
        sec = f"{i % 60:02d}"
        min_val = f"{(i // 60) + 1:02d}"
        # Synthetic character name
        char_name = f"Hero_{i}"
        level = i + 1

        # Periodic chat or zone transition noise
        if i % 5 == 0:
            lines.append(f"{ts_base}{min_val}:{sec} 123456 [INFO Client 1234] @To Guildie: on my way to boss")
        if i % 10 == 0:
            lines.append(f"{ts_base}{min_val}:{sec} 123456 [INFO Client 1234] : Generating level {level} area \"Crypt of Secrets\"")
            lines.append(f"{ts_base}{min_val}:{sec} 123456 [INFO Client 1234] : Entered area \"Crypt of Secrets\"")
        if i % 15 == 0:
            lines.append(f"{ts_base}{min_val}:{sec} 123456 [INFO Client 1234] #Global 1: Anyone know where the trial is?")

        # PoE2 format level-up line
        lines.append(f"{ts_base}{min_val}:{sec} 123456 [INFO Client 1234] : {char_name} ({cls}) is now level {level}")

    lines.append(f"{ts_base}59:59 123456 [INFO Client 1234] %PartyLeader: gg thanks for party")
    return lines


def test_49_poe2_level_ups_regression(tmp_path: Path) -> None:
    log_lines = _generate_synthetic_poe2_log_stream()
    log_file = tmp_path / "Client.txt"
    with open(log_file, "wb") as f:
        for line in log_lines:
            f.write(f"{line}\n".encode("utf-8"))

    tailer = ClientLogTailer(log_file)
    all_events: list[ParsedLogEvent] = []

    # Tail using small batches (max_lines=15) to exercise multi-batch streaming
    batch_size = 15
    while True:
        batch = tailer.poll(max_lines=batch_size)
        if not batch:
            break
        assert len(batch) <= batch_size
        all_events.extend(batch)

    # 1. Total level-up events must be exactly 49
    level_ups = [e for e in all_events if e.event_type == ParsedLogEventType.LEVEL_UP]
    assert len(level_ups) == 49

    # 2. Each level up has valid character name, level, and character_class
    for idx, ev in enumerate(level_ups, start=1):
        assert ev.payload["character_name"] == f"Hero_{idx}"
        assert ev.payload["level"] == idx + 1
        assert "character_class" in ev.payload
        assert ev.payload["character_class"] in ["Mercenary", "Warrior", "Sorceress", "Monk", "Ranger", "Witch"]

    # 3. Privacy filter: zero chat events emitted
    for ev in all_events:
        for val in ev.payload.values():
            if isinstance(val, str):
                assert not val.startswith("@From")
                assert not val.startswith("@To")
                assert not val.startswith("$")
                assert not val.startswith("#")
                assert not val.startswith("%")
                assert "TraderBob" not in val
                assert "SpamBot" not in val
                assert "Guildie" not in val


def test_real_log_regression_chat_filtering() -> None:
    chat_samples = [
        "2026/09/22 10:00:00 123456 [INFO Client 1234] @From Exile_1: level 100 already? crazy",
        "2026/09/22 10:00:01 123456 [INFO Client 1234] @To Friend: : BOMSHAK (Mercenary) is now level 11",
        "2026/09/22 10:00:02 123456 [INFO Client 1234] $Trade: 50 divine orbs for mirror",
        "2026/09/22 10:00:03 123456 [INFO Client 1234] #English: is mercenary good?",
        "2026/09/22 10:00:04 123456 [INFO Client 1234] %Party: teleport to me",
    ]
    for sample in chat_samples:
        ev = parse_log_line(sample)
        assert ev is None, f"Expected chat sample to be filtered out, got {ev}"
