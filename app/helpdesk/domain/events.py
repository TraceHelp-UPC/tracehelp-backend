"""Eventos de dominio del contexto Helpdesk."""
import uuid
from dataclasses import dataclass

from app.shared.domain.aggregate_root import DomainEvent


@dataclass(frozen=True, kw_only=True)
class TicketRegistered(DomainEvent):
    """Se emite al registrar un incidente. Smart Triage lo escucha para iniciar el triaje."""

    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    reporter_id: uuid.UUID
    has_evidence: bool


@dataclass(frozen=True, kw_only=True)
class TicketStatusChanged(DomainEvent):
    """Se emite en cada cambio de estado válido. Lo usarán las notificaciones (US19) y la auditoría."""

    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    reporter_id: uuid.UUID
    previous_status: str
    new_status: str
    changed_by: uuid.UUID | None
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class TicketClassificationOverridden(DomainEvent):
    """Se emite cuando un analista corrige la categoría o prioridad sugerida en el triaje (US27, T42)."""

    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    analyst_id: uuid.UUID
    suggested_category: str
    suggested_priority: str
    new_category: str
    new_priority: str
