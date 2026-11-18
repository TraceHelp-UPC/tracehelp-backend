"""Eventos de dominio del contexto Smart Triage."""
import uuid
from dataclasses import dataclass

from app.shared.domain.aggregate_root import DomainEvent


@dataclass(frozen=True, kw_only=True)
class LowConfidenceAlertRaised(DomainEvent):
    """Ningún fragmento de los manuales superó el umbral de evidencia (US11).

    No se genera respuesta automática: el ticket lo resuelve un analista. La bitácora de auditoría (T36) lo registra.
    """

    workspace_id: uuid.UUID
    ticket_id: uuid.UUID | None
    best_score: float
    similarity_threshold: float
    fragments_retrieved: int


@dataclass(frozen=True, kw_only=True)
class TriageCompleted(DomainEvent):
    """El triaje automático de un ticket terminó (T28).

    Helpdesk lo escucha para mover el ticket a `route` (SELF_SERVICE_PROPOSED o PENDING_ASSIGNMENT)
    y aplicar la clasificación sugerida (US27, T41).
    """

    diagnosis_id: uuid.UUID
    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    outcome: str
    confidence_level: str | None
    best_score: float | None
    route: str
    suggested_category: str | None = None
    suggested_priority: str | None = None


@dataclass(frozen=True, kw_only=True)
class AiResolutionReviewed(DomainEvent):
    """Un analista revisó la respuesta de la IA (US15, T35): aprobó, editó, rechazó o respondió manualmente.

    La bitácora de auditoría (T36) lo registra.
    """

    diagnosis_id: uuid.UUID
    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    reviewer_id: uuid.UUID
    decision: str
    previous_status: str
    ai_outcome: str
    resolves_ticket: bool
    note: str | None = None
