"""Clases base del dominio compartidas por todos los contextos."""
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Evento de dominio. Cada contexto define sus eventos heredando de esta clase."""

    occurred_on: datetime = field(default_factory=lambda: datetime.now(UTC))


class AggregateRoot:
    """Raíz de agregado que acumula los eventos de dominio hasta que la capa de aplicación los publica."""

    def __init__(self) -> None:
        self._events: list[DomainEvent] = []

    def record_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        events, self._events = self._events, []
        return events
