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
