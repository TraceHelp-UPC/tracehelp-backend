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
class TicketClassificationCorrected(DomainEvent):
    """Se emite cuando un analista establece o corrige la categoría o prioridad del ticket (US27, T42)."""

    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    corrected_by: uuid.UUID
    previous_category: str | None
    new_category: str | None
    previous_priority: str
    new_priority: str
    reason: str | None = None
