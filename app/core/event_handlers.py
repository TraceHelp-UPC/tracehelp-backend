"""Registro central de suscripciones del bus de eventos.

Cada módulo agrega aquí sus manejadores cuando los implemente, por ejemplo:
    bus.subscribe(TicketRegistered, triage_on_ticket_registered)      # T28 (Smart Triage)
    bus.subscribe(DomainEvent, analytics_audit_handler)                # T36 (Analytics)
"""
from app.core.config import get_settings
from app.knowledge.domain.events import TechnicalDocumentUploaded
from app.shared.infrastructure.event_bus import InMemoryEventBus


def register_event_handlers(bus: InMemoryEventBus) -> None:
    """Se llama una vez al crear la aplicación."""
    if get_settings().ingestion_worker_enabled:
        from app.knowledge.infrastructure.ingestion_worker import ingestion_worker

        # T23: cada manual cargado se procesa en segundo plano
        bus.subscribe(TechnicalDocumentUploaded, ingestion_worker.on_document_uploaded)
