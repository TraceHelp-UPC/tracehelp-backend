"""Registro central de suscripciones del bus de eventos.

Cada módulo agrega aquí sus manejadores cuando los implemente, por ejemplo:
    bus.subscribe(TicketRegistered, triage_on_ticket_registered)      # T28 (Smart Triage)
    bus.subscribe(DomainEvent, analytics_audit_handler)                # T36 (Analytics)
"""
from app.shared.infrastructure.event_bus import InMemoryEventBus


def register_event_handlers(bus: InMemoryEventBus) -> None:
    """Se llama una vez al crear la aplicación."""
