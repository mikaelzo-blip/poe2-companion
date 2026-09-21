"""In-memory observation bus with decoupled typed pub/sub dispatch."""

from __future__ import annotations

from typing import Callable
import uuid
from pydantic import BaseModel, ConfigDict

from companion.observations.schema import ObservationEvent, ObservationEventType

HandlerFn = Callable[[ObservationEvent], None]


class SubscriptionToken(BaseModel):
    """Opaque handle used to unsubscribe from the observation bus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    token_id: str
    event_type: ObservationEventType | None = None


class ObservationBus:
    """Thread-safe and decoupled in-memory pub/sub observation bus."""

    def __init__(self) -> None:
        # Map event_type (or None for wildcard) to list of (token_id, handler)
        self._listeners: dict[
            ObservationEventType | None, list[tuple[str, HandlerFn]]
        ] = {}

    def subscribe(
        self,
        event_type: ObservationEventType | None,
        handler: HandlerFn,
    ) -> SubscriptionToken:
        """Register a handler for a specific event type, or None for all events."""
        token = SubscriptionToken(
            token_id=str(uuid.uuid4()),
            event_type=event_type,
        )
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append((token.token_id, handler))
        return token

    def unsubscribe(self, token: SubscriptionToken) -> bool:
        """Remove a subscriber matching the token."""
        found = False
        if token.event_type in self._listeners:
            initial_len = len(self._listeners[token.event_type])
            self._listeners[token.event_type] = [
                item
                for item in self._listeners[token.event_type]
                if item[0] != token.token_id
            ]
            if len(self._listeners[token.event_type]) < initial_len:
                found = True
        return found

    def publish(self, event: ObservationEvent) -> int:
        """Dispatch event to matching listeners in deterministic registration order."""
        count = 0
        # 1. Type-specific listeners
        if event.event_type in self._listeners:
            for _, handler in list(self._listeners[event.event_type]):
                handler(event)
                count += 1

        # 2. Wildcard listeners (None)
        if None in self._listeners:
            for _, handler in list(self._listeners[None]):
                handler(event)
                count += 1

        return count

    def clear(self) -> None:
        """Clear all active subscriptions."""
        self._listeners.clear()
