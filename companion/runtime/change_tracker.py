"""State change tracking and batch coalescing for continuous runtime."""

from __future__ import annotations

from enum import Enum

from companion.state.schema import CharacterState


class DirtyTrigger(str, Enum):
    """Specific triggers indicating character state mutations."""

    LEVEL = "level"
    ZONE = "zone"
    SESSION_STATE = "session_state"
    CHARACTER_IDENTITY = "character_identity"
    GEAR_AUDIT = "gear_audit"
    DEATH_COUNT = "death_count"


OBJECTIVE_REEVALUATION_TRIGGERS = {
    DirtyTrigger.LEVEL,
    DirtyTrigger.ZONE,
    DirtyTrigger.CHARACTER_IDENTITY,
    DirtyTrigger.GEAR_AUDIT,
}


class StateChangeTracker:
    """Tracks state delta across log batches to coalesce objective derivations."""

    def __init__(self) -> None:
        self._active_triggers: set[DirtyTrigger] = set()

    @property
    def active_triggers(self) -> set[DirtyTrigger]:
        return set(self._active_triggers)

    def compute_delta(
        self,
        previous_state: CharacterState | None,
        current_state: CharacterState,
    ) -> set[DirtyTrigger]:
        """Compute dirty triggers between two character states and record them."""
        triggers: set[DirtyTrigger] = set()

        if previous_state is None:
            triggers.add(DirtyTrigger.CHARACTER_IDENTITY)
            if current_state.level.value is not None:
                triggers.add(DirtyTrigger.LEVEL)
            if current_state.current_zone.value is not None:
                triggers.add(DirtyTrigger.ZONE)
            self._active_triggers.update(triggers)
            return triggers

        if current_state.character_id != previous_state.character_id or current_state.character_name != previous_state.character_name:
            triggers.add(DirtyTrigger.CHARACTER_IDENTITY)

        if current_state.level.value != previous_state.level.value:
            triggers.add(DirtyTrigger.LEVEL)

        if (
            current_state.current_zone.value != previous_state.current_zone.value
            or current_state.current_act.value != previous_state.current_act.value
        ):
            triggers.add(DirtyTrigger.ZONE)

        if current_state.session_active != previous_state.session_active:
            triggers.add(DirtyTrigger.SESSION_STATE)

        if current_state.death_count.value != previous_state.death_count.value:
            triggers.add(DirtyTrigger.DEATH_COUNT)

        self._active_triggers.update(triggers)
        return triggers

    def has_changes(self) -> bool:
        """Return True if any dirty trigger is currently recorded."""
        return len(self._active_triggers) > 0

    def should_reevaluate_objectives(self) -> bool:
        """Return True if active dirty triggers require reevaluating objectives."""
        return bool(self._active_triggers.intersection(OBJECTIVE_REEVALUATION_TRIGGERS))

    def clear(self) -> None:
        """Clear active dirty triggers after batch cycle finishes."""
        self._active_triggers.clear()
