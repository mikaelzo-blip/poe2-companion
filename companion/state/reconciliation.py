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

    state.last_observed_at = ts_iso
    state.updated_at = datetime.now(timezone.utc).isoformat()
    return state
