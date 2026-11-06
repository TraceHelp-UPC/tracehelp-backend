"""Eventos de dominio del Bounded Context Smart Triage."""
import uuid
from dataclasses import dataclass, field

from app.shared.domain.aggregate_root import DomainEvent


@dataclass(frozen=True, kw_only=True)
class RagRecommendationGenerated(DomainEvent):
    """Se emite cuando el motor RAG sintetiza una recomendación fundamentada con citas (US11)."""

    diagnosis_id: uuid.UUID
    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    confidence_score: float
    consulted_sources: list[dict] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class LowConfidenceAlertTriggered(DomainEvent):
    """Se emite cuando no hay fuentes o el puntaje es inferior al umbral 0.70 (US11)."""

    diagnosis_id: uuid.UUID
    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    confidence_score: float
    reason: str


@dataclass(frozen=True, kw_only=True)
class AiResolutionReviewed(DomainEvent):
    """Se emite tras la revisión humana HITL por el analista de soporte (US15, T35)."""

    diagnosis_id: uuid.UUID
    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    reviewer_id: uuid.UUID
    action: str
    final_text: str | None = None
    consulted_sources: list[dict] = field(default_factory=list)
    confidence_score: float | None = None
