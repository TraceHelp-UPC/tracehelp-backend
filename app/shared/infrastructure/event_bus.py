"""Bus de eventos de dominio en memoria (in-process) del monolito modular.

Los módulos se comunican publicando eventos de dominio (por ejemplo, TicketRegistered) sin importarse entre sí.
Los manejadores se ejecutan de forma síncrona, en el mismo proceso, en el orden en que se suscribieron.

Reglas de uso:
- Publicar los eventos DESPUÉS de hacer commit de la transacción, para no notificar cambios que se revirtieron.
- Un manejador que falla se registra en el log y no impide que se ejecuten los demás.
- Un manejador suscrito a una clase base (por ejemplo, DomainEvent) recibe también sus subclases.
"""
import logging
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import TypeVar

from app.shared.domain.aggregate_root import DomainEvent

logger = logging.getLogger(__name__)

E = TypeVar("E", bound=DomainEvent)
Handler = Callable[[E], None]


class InMemoryEventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type[E], handler: Handler) -> None:
        """Registra un manejador para un tipo de evento. Registrar el mismo manejador dos veces no lo duplica."""
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[E], handler: Handler) -> None:
        if handler in self._handlers.get(event_type, []):
            self._handlers[event_type].remove(handler)

    def handlers_for(self, event_type: type[DomainEvent]) -> list[Handler]:
        """Manejadores del tipo exacto y de sus clases base, en orden de la jerarquía."""
        handlers: list[Handler] = []
        for cls in event_type.__mro__:
            for handler in self._handlers.get(cls, []):
                if handler not in handlers:
                    handlers.append(handler)
        return handlers

    def publish(self, event: DomainEvent) -> None:
        for handler in self.handlers_for(type(event)):
            try:
                handler(event)
            except Exception:  # noqa: BLE001 - un manejador no debe romper a los demás ni al publicador
                logger.exception("Error en el manejador %s del evento %s", getattr(handler, "__qualname__", handler), type(event).__name__)

    def publish_all(self, events: Iterable[DomainEvent]) -> None:
        for event in events:
            self.publish(event)

    def clear(self) -> None:
        """Quita todas las suscripciones (útil en pruebas)."""
        self._handlers.clear()


# Instancia única compartida por todo el backend
event_bus = InMemoryEventBus()


def get_event_bus() -> InMemoryEventBus:
    """Dependencia de FastAPI para inyectar el bus en los servicios de aplicación."""
    return event_bus
