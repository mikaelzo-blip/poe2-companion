"""State reconciler mapping observation events to CharacterState facts."""

from __future__ import annotations

from datetime import datetime, timezone
from companion.observations.schema import ObservationEvent, ObservationEventType
from companion.state.provenance import ProvenancedField, VerificationState
from companion.state.schema import CharacterState


def reconcile_observation(
    state: CharacterState,
    event: ObservationEvent,
) -> CharacterState:
    """Apply an incoming observation event to character state with provenance."""
    src = event.source.value
    ts_iso = event.timestamp.isoformat()

    if event.event_type == ObservationEventType.LEVEL_UP:
        new_level = event.payload.get("level")
        char_name = event.payload.get("character_name")
        # Match character name if specified
        if char_name is None or char_name == state.character_name:
            if new_level is not None and new_level > state.level.value:
                state.level = ProvenancedField.create(
                    new_level,
                    src,
                    VerificationState.VERIFIED,
                    observed_at=ts_iso,
                )

    elif event.event_type == ObservationEventType.ZONE_TRANSITION:
        zone = event.payload.get("zone")
        if zone:
            state.current_zone = ProvenancedField.create(
                zone,
                src,
                VerificationState.VERIFIED,
                observed_at=ts_iso,
            )

    elif event.event_type == ObservationEventType.DEATH:
        char_name = event.payload.get("character_name")
        if char_name is None or char_name == state.character_name:
            source_stream_id = event.payload.get("source_stream_id")
            end_offset = event.payload.get("end_offset")

            if source_stream_id is not None and end_offset is not None:
                watermark_stream_id: str | None = None
                watermark_end_offset: int | None = None
                for ref in (state.death_count.evidence_refs if state.death_count else []):
                    if ref.startswith("watermark:"):
                        remainder = ref[len("watermark:"):]
                        if ":" in remainder:
                            w_stream, w_off = remainder.rsplit(":", 1)
                            try:
                                watermark_stream_id = w_stream
                                watermark_end_offset = int(w_off)
                            except ValueError:
                                pass

                if (
                    watermark_stream_id is not None
                    and watermark_end_offset is not None
                    and source_stream_id == watermark_stream_id
                    and int(end_offset) <= watermark_end_offset
                ):
                    # Already counted; idempotent no-op
                    return state

                curr_deaths = state.death_count.value if state.death_count else 0
                new_watermark = f"watermark:{source_stream_id}:{end_offset}"
                state.death_count = ProvenancedField.create(
                    curr_deaths + 1,
                    src,
                    VerificationState.VERIFIED,
                    observed_at=ts_iso,
                    evidence_refs=[new_watermark],
                )
            else:
                curr_deaths = state.death_count.value if state.death_count else 0
                state.death_count = ProvenancedField.create(
                    curr_deaths + 1,
                    src,
                    VerificationState.VERIFIED,
                    observed_at=ts_iso,
                )

    elif event.event_type == ObservationEventType.PROCESS_STATE_CHANGE:
        proc_state = event.payload.get("state")
        state.session_active = (proc_state == "RUNNING")

    elif event.event_type == ObservationEventType.STAT_OBSERVATION:
        ver_state_str = event.payload.get("verification_state", "VERIFIED")
        try:
            ver_state = VerificationState(ver_state_str)
        except ValueError:
            ver_state = VerificationState.UNKNOWN

        resists = event.payload.get("resistances", {})
        for r_key, r_val in resists.items():
            if r_val is not None and r_key in state.resistances:
                state.resistances[r_key] = ProvenancedField.create(
                    r_val,
                    src,
                    ver_state,
                    observed_at=ts_iso,
                )

    state.last_observed_at = ts_iso
    state.updated_at = datetime.now(timezone.utc).isoformat()
    return state
