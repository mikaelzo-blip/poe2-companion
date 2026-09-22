"""Unit tests for durable counted-event watermark idempotency on death_count."""

from __future__ import annotations

from companion.observations.schema import ObservationEvent, ObservationEventType, ObservationSource
from companion.runtime.normalizer import build_observation_id, build_source_stream_id, normalize_log_event
from companion.sensing.client_log import ParsedLogEvent, ParsedLogEventType
from companion.state.reconciliation import reconcile_observation
from companion.state.schema import CharacterState


def test_death_increments_and_sets_watermark() -> None:
    char = CharacterState(character_id="Witch", character_name="Witch")
    assert char.death_count.value == 0

    parsed = ParsedLogEvent(
        event_type=ParsedLogEventType.DEATH,
        payload={"character_name": "Witch"},
    )
    obs = normalize_log_event(
        parsed_event=parsed,
        source_stream_id="stream1:epoch_1",
        start_offset=100,
        end_offset=200,
        character_id="Witch",
    )

    reconciled = reconcile_observation(char, obs)
    assert reconciled.death_count.value == 1
    assert any("watermark:stream1:epoch_1:200" in ref for ref in reconciled.death_count.evidence_refs)


def test_replaying_death_event_is_idempotent() -> None:
    char = CharacterState(character_id="Witch", character_name="Witch")
    parsed = ParsedLogEvent(
        event_type=ParsedLogEventType.DEATH,
        payload={"character_name": "Witch"},
    )
    obs = normalize_log_event(
        parsed_event=parsed,
        source_stream_id="stream1:epoch_1",
        start_offset=100,
        end_offset=200,
        character_id="Witch",
    )

    reconciled = reconcile_observation(char, obs)
    assert reconciled.death_count.value == 1

    # Replay the exact same event
    reconciled_again = reconcile_observation(reconciled, obs)
    assert reconciled_again.death_count.value == 1  # Unchanged!


def test_replaying_large_batch_over_100_deaths_is_idempotent() -> None:
    char = CharacterState(character_id="Witch", character_name="Witch")
    stream_id = "stream1:epoch_1"

    # Generate 150 death events with increasing offsets
    events: list[ObservationEvent] = []
    current_offset = 0
    for i in range(150):
        start = current_offset
        end = start + 50
        current_offset = end
        parsed = ParsedLogEvent(
            event_type=ParsedLogEventType.DEATH,
            payload={"character_name": "Witch"},
        )
        obs = normalize_log_event(
            parsed_event=parsed,
            source_stream_id=stream_id,
            start_offset=start,
            end_offset=end,
            character_id="Witch",
        )
        events.append(obs)

    # First pass: all 150 events processed
    for ev in events:
        char = reconcile_observation(char, ev)

    assert char.death_count.value == 150
    assert any(f"watermark:{stream_id}:{current_offset}" in ref for ref in char.death_count.evidence_refs)

    # Replay all 150 events (simulating crash before checkpoint)
    for ev in events:
        char = reconcile_observation(char, ev)

    assert char.death_count.value == 150  # Must still be 150, zero double-counting!


def test_distinct_death_events_advance_counter_and_watermark() -> None:
    char = CharacterState(character_id="Witch", character_name="Witch")
    stream_id = "stream1:epoch_1"

    ev1 = normalize_log_event(
        parsed_event=ParsedLogEvent(event_type=ParsedLogEventType.DEATH, payload={"character_name": "Witch"}),
        source_stream_id=stream_id,
        start_offset=10,
        end_offset=50,
        character_id="Witch",
    )
    ev2 = normalize_log_event(
        parsed_event=ParsedLogEvent(event_type=ParsedLogEventType.DEATH, payload={"character_name": "Witch"}),
        source_stream_id=stream_id,
        start_offset=60,
        end_offset=100,
        character_id="Witch",
    )

    char = reconcile_observation(char, ev1)
    assert char.death_count.value == 1

    char = reconcile_observation(char, ev2)
    assert char.death_count.value == 2
    assert any(f"watermark:{stream_id}:100" in ref for ref in char.death_count.evidence_refs)


def test_new_stream_epoch_resets_watermark_and_counts_death() -> None:
    char = CharacterState(character_id="Witch", character_name="Witch")
    ev_epoch1 = normalize_log_event(
        parsed_event=ParsedLogEvent(event_type=ParsedLogEventType.DEATH, payload={"character_name": "Witch"}),
        source_stream_id="stream1:epoch_1",
        start_offset=500,
        end_offset=550,
        character_id="Witch",
    )
    char = reconcile_observation(char, ev_epoch1)
    assert char.death_count.value == 1

    # After truncation, epoch is 2 and offsets restart from 0
    ev_epoch2 = normalize_log_event(
        parsed_event=ParsedLogEvent(event_type=ParsedLogEventType.DEATH, payload={"character_name": "Witch"}),
        source_stream_id="stream1:epoch_2",
        start_offset=10,
        end_offset=60,
        character_id="Witch",
    )
    char = reconcile_observation(char, ev_epoch2)
    assert char.death_count.value == 2
    assert any("watermark:stream1:epoch_2:60" in ref for ref in char.death_count.evidence_refs)
