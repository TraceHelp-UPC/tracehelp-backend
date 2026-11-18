"""Manejador de TriageCompleted: mueve el ticket según el resultado del triaje automático (T28).

Smart Triage decide la ruta y Helpdesk aplica el cambio con su propia máquina de estados, así cada contexto
modifica solo sus propias tablas. Se ejecuta en el hilo del worker de triaje, con una sesión propia.
"""
import logging

from app.core.database import SessionLocal
from app.helpdesk.application.ticket_command_service import TicketCommandService
from app.helpdesk.domain.enums import TicketCategory, TicketPriority, TicketStatus
from app.helpdesk.infrastructure.image_processor import PillowImageProcessor
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.shared.infrastructure.event_bus import InMemoryEventBus, event_bus
from app.smart_triage.domain.events import TriageCompleted

logger = logging.getLogger(__name__)

_REASONS = {
    "ANSWERED": "la IA encontró una solución en los manuales",
    "INSUFFICIENT_EVIDENCE": "los manuales no tienen información suficiente",
    "MODEL_DECLINED": "la IA indicó que los manuales no resuelven el incidente",
    "INVALID_RESPONSE": "la respuesta de la IA no tenía citas válidas",
    "PROVIDER_ERROR": "el servicio de IA no estuvo disponible",
}


def routing_reason(event: TriageCompleted) -> str:
    detail = _REASONS.get(event.outcome, event.outcome)
    if event.route == TicketStatus.SELF_SERVICE_PROPOSED.value:
        return f"Triaje automático: {detail}; se propone al colaborador como autoservicio."
    if event.outcome == "ANSWERED":
        return f"Triaje automático: {detail}; queda para validación de un analista."
    return f"Triaje automático: {detail}; queda para atención de un analista."


class TriageRoutingHandler:
    def __init__(self, session_factory=SessionLocal, events: InMemoryEventBus = event_bus) -> None:
        self._session_factory = session_factory
        self._events = events

    def __call__(self, event: TriageCompleted) -> None:
        with self._session_factory() as session:
            service = TicketCommandService(
                session=session,
                tickets=SqlAlchemyTicketRepository(session),
                images=PillowImageProcessor(),
                events=self._events,
            )
            category = TicketCategory(event.suggested_category) if event.suggested_category else None
            priority = TicketPriority(event.suggested_priority) if event.suggested_priority else None
            service.route_after_triage(
                event.ticket_id,
                TicketStatus(event.route),
                routing_reason(event),
                suggested_category=category,
                suggested_priority=priority,
            )
