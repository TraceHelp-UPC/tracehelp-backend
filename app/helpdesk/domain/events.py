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


@dataclass(frozen=True, kw_only=True)
class MessagePosted(DomainEvent):
    """Mensaje o nota interna registrada en el ticket (US26). No lleva el texto: lo consumen T91 y la auditoría."""

    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    message_id: uuid.UUID
    ticket_code: str
    author_id: uuid.UUID
    reporter_id: uuid.UUID
    assigned_analyst_id: uuid.UUID | None
    author_is_reporter: bool
    is_internal_note: bool
    ticket_status: str
    content_length: int


@dataclass(frozen=True, kw_only=True)
class TicketEscalated(DomainEvent):
    """Se emite cuando un analista L1 escala un ticket a un grupo especialista L2 (US17, T79)."""

    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    escalated_by: uuid.UUID
    specialist_group: str
    assigned_analyst_id: uuid.UUID | None
    has_triage_snapshot: bool
    reason: str


@dataclass(frozen=True, kw_only=True)
class TicketReturnedToL1(DomainEvent):
    """Se emite cuando un especialista L2 devuelve un ticket escalado al analista L1 original (US17, T79)."""

    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    returned_by: uuid.UUID
    assigned_analyst_id: uuid.UUID | None
    escalated_group: str | None
    reason: str


@dataclass(frozen=True, kw_only=True)
class SelfServiceAccepted(DomainEvent):
    """El colaborador confirmó que la recomendación de autoservicio resolvió el incidente (US12, T76)."""

    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    reporter_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class SelfServiceRejected(DomainEvent):
    """El colaborador rechazó la recomendación de autoservicio y derivó el incidente a soporte L1 (US12, T76)."""

    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    reporter_id: uuid.UUID
    reason: str | None = None
