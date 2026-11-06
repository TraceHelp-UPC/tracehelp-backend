"""Casos de uso de bitácora de auditoría y consumo de eventos del Bounded Context Analytics (US15, T36)."""
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.analytics.domain.audit_trail_entry import AuditTrailEntry
from app.analytics.domain.enums import AuditActionType
from app.analytics.domain.exceptions import InvalidAuditLogDataError
from app.analytics.domain.repositories import IAuditTrailRepository
from app.shared.domain.aggregate_root import DomainEvent


@dataclass(frozen=True)
class RecordAuditEntryCommand:
    workspace_id: uuid.UUID
    ticket_id: uuid.UUID
    action_type: AuditActionType
    consulted_sources: list[dict] = field(default_factory=list)
    validator_analyst_id: uuid.UUID | None = None
    confidence_score: float | None = None
    details: str | None = None
    occurred_at: datetime | None = None


class AuditTrailService:
    """Servicio de aplicación para registrar y consultar la bitácora inmutable de auditoría."""

    def __init__(self, session: Session, repository: IAuditTrailRepository) -> None:
        self._session = session
        self._repository = repository

    def record_entry(self, command: RecordAuditEntryCommand) -> AuditTrailEntry:
        entry = AuditTrailEntry.record(
            workspace_id=command.workspace_id,
            ticket_id=command.ticket_id,
            action_type=command.action_type,
            consulted_sources=command.consulted_sources,
            validator_analyst_id=command.validator_analyst_id,
            confidence_score=command.confidence_score,
            details=command.details,
            occurred_at=command.occurred_at,
        )
        self._repository.append(entry)
        self._session.commit()
        return entry

    def get_ticket_audit_trail(self, ticket_id: uuid.UUID, workspace_id: uuid.UUID) -> list[AuditTrailEntry]:
        return self._repository.find_by_ticket(ticket_id=ticket_id, workspace_id=workspace_id)

    def list_workspace_logs(
        self,
        workspace_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        ticket_id: uuid.UUID | None = None,
    ) -> tuple[list[AuditTrailEntry], int]:
        if page < 1:
            raise InvalidAuditLogDataError("El número de página debe ser mayor o igual a 1.")
        if page_size < 1 or page_size > 100:
            raise InvalidAuditLogDataError("El tamaño de página debe estar entre 1 y 100.")
        return self._repository.list_by_workspace(
            workspace_id=workspace_id, page=page, page_size=page_size, ticket_id=ticket_id
        )

    def handle_domain_event(self, event: DomainEvent) -> AuditTrailEntry | None:
        """Traduce un evento de dominio a una entrada inmutable de auditoría (ACL)."""
        command = translate_event_to_audit_command(event)
        if command is None:
            return None
        return self.record_entry(command)


def translate_event_to_audit_command(event: DomainEvent) -> RecordAuditEntryCommand | None:
    """Anti-Corruption Layer: traduce eventos de Helpdesk y Smart Triage a RecordAuditEntryCommand."""
    ticket_id = getattr(event, "ticket_id", None)
    workspace_id = getattr(event, "workspace_id", None)
    if ticket_id is None or workspace_id is None:
        return None

    event_name = type(event).__name__
    sources = list(getattr(event, "consulted_sources", None) or getattr(event, "citations", None) or [])
    confidence = getattr(event, "confidence_score", None)
    occurred_at = getattr(event, "occurred_at", None)

    if event_name == "TicketStatusChanged":
        prev = getattr(event, "previous_status", "")
        new = getattr(event, "new_status", "")
        reason = getattr(event, "reason", None)
        details = f"{prev} -> {new}" + (f" ({reason})" if reason else "")
        return RecordAuditEntryCommand(
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            action_type=AuditActionType.TICKET_STATUS_CHANGED,
            validator_analyst_id=getattr(event, "changed_by", None),
            details=details,
            occurred_at=occurred_at,
        )

    if event_name in {"RagRecommendationGenerated", "RagRecommendationGeneratedEvent"}:
        return RecordAuditEntryCommand(
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            action_type=AuditActionType.RAG_RECOMMENDATION_GENERATED,
            consulted_sources=sources,
            confidence_score=confidence,
            details=getattr(event, "summary", None) or "Recomendación RAG generada con citas verificadas",
            occurred_at=occurred_at,
        )

    if event_name in {
        "LowConfidenceAlertTriggered",
        "LowConfidenceAlertRegistered",
        "LowConfidenceAlertRegisteredEvent",
    }:
        return RecordAuditEntryCommand(
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            action_type=AuditActionType.LOW_CONFIDENCE_ALERT_TRIGGERED,
            consulted_sources=sources,
            confidence_score=confidence,
            details=getattr(event, "reason", None) or "Alerta de baja confianza o falta de evidencia documental",
            occurred_at=occurred_at,
        )

    if event_name in {"AiResolutionReviewed", "AiResolutionReviewedEvent"}:
        review_action = str(getattr(event, "action", "APPROVE")).upper()
        action_map = {
            "APPROVE": AuditActionType.AI_RESOLUTION_APPROVED,
            "APPROVED": AuditActionType.AI_RESOLUTION_APPROVED,
            "EDIT": AuditActionType.AI_RESOLUTION_EDITED,
            "EDITED": AuditActionType.AI_RESOLUTION_EDITED,
            "EDIT_AND_APPROVE": AuditActionType.AI_RESOLUTION_EDITED,
            "REJECT": AuditActionType.AI_RESOLUTION_REJECTED,
            "REJECTED": AuditActionType.AI_RESOLUTION_REJECTED,
            "MANUAL": AuditActionType.MANUAL_RESOLUTION_PROVIDED,
            "MANUAL_RESPONSE": AuditActionType.MANUAL_RESOLUTION_PROVIDED,
        }
        audit_action = action_map.get(review_action, AuditActionType.AI_RESOLUTION_APPROVED)
        analyst_id = getattr(event, "reviewer_id", None) or getattr(event, "validator_analyst_id", None)
        return RecordAuditEntryCommand(
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            action_type=audit_action,
            consulted_sources=sources,
            validator_analyst_id=analyst_id,
            confidence_score=confidence,
            details=getattr(event, "details", None) or f"Revisión humana HITL: {review_action}",
            occurred_at=occurred_at,
        )

    if event_name in {"TicketClassificationOverridden", "ClassificationOverridden"}:
        return RecordAuditEntryCommand(
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            action_type=AuditActionType.CLASSIFICATION_OVERRIDDEN,
            validator_analyst_id=getattr(event, "analyst_id", None),
            details=getattr(event, "details", None) or "Corrección manual de categoría y prioridad",
            occurred_at=occurred_at,
        )

    return None
