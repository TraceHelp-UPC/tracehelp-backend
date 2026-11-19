"""Registro central de suscripciones del bus de eventos.

Cada módulo agrega aquí sus manejadores cuando los implementa, por ejemplo:
    bus.subscribe(DomainEvent, analytics_audit_handler)                # T36 (Analytics)
"""
from app.analytics.application.audit_log_service import AuditEventHandler
from app.core.config import get_settings
from app.helpdesk.domain.events import SelfServiceRejected, TicketRegistered, TicketStatusChanged
from app.knowledge.domain.events import TechnicalDocumentUploaded
from app.shared.domain.aggregate_root import DomainEvent
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.domain.events import TriageCompleted
from app.smart_triage.infrastructure.self_service_rejection_handler import SelfServiceRejectionHandler

analytics_audit_handler = AuditEventHandler()
self_service_rejection_handler = SelfServiceRejectionHandler()


def register_event_handlers(bus: InMemoryEventBus) -> None:
    """Se llama una vez al crear la aplicación."""
    settings = get_settings()
    if settings.ingestion_worker_enabled:
        from app.knowledge.infrastructure.ingestion_worker import ingestion_worker

        # T23: cada manual cargado se procesa en segundo plano
        bus.subscribe(TechnicalDocumentUploaded, ingestion_worker.on_document_uploaded)

    if settings.triage_worker_enabled:
        from app.helpdesk.infrastructure.triage_routing import TriageRoutingHandler
        from app.smart_triage.infrastructure.triage_worker import triage_worker

        # T28: cada ticket registrado se tría en segundo plano y Helpdesk lo mueve según el resultado
        bus.subscribe(TicketRegistered, triage_worker.on_ticket_registered)
        bus.subscribe(TriageCompleted, TriageRoutingHandler(events=bus))

    # T76 (US12, D10): siempre activo (incluso sin triage worker) y registrado antes de asignación automática (T72)
    bus.subscribe(SelfServiceRejected, self_service_rejection_handler)
    bus.subscribe(TicketStatusChanged, self_service_rejection_handler)

    # T36: cada evento de dominio relevante se registra en la bitácora de auditoría inmutable
    bus.subscribe(DomainEvent, analytics_audit_handler)
