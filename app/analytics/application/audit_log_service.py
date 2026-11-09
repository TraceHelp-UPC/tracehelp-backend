"""Servicio de aplicación y manejador de eventos para la bitácora de auditoría (US15, T36)."""
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.analytics.domain.audit_entry import AuditEntry
from app.analytics.domain.repositories import AuditLogFilter, IAuditLogRepository
from app.analytics.infrastructure.persistence.audit_log_repository import SqlAlchemyAuditLogRepository
from app.core.database import SessionLocal
from app.shared.domain.aggregate_root import DomainEvent
from app.shared.domain.pagination import Page, PageRequest
from app.shared.domain.pii import IPiiMasker
from app.shared.infrastructure.pii_masker import get_pii_masker

# Campos de texto libre que se enmascaran con RegexSpacyPiiMasker antes de guardarse en detail
_TEXT_FIELDS = {"reason", "note"}


@dataclass(frozen=True)
class AuditLogItemView:
    id: uuid.UUID
    workspace_id: uuid.UUID
    event_type: str
    actor_id: uuid.UUID | None
    actor_name: str
    entity_type: str
    entity_id: uuid.UUID | None
    ticket_id: uuid.UUID | None
    detail: dict[str, Any]
    integrity_hash: str
    occurred_at: datetime


class AuditLogService:
    """Servicio de consulta paginada y registro de la bitácora de auditoría."""

    def __init__(
        self,
        repository: IAuditLogRepository,
        user_names: Callable[[set[uuid.UUID]], dict[uuid.UUID, str]] | None = None,
    ) -> None:
        self._repository = repository
        self._user_names = user_names or (lambda _: {})

    def query(self, criteria: AuditLogFilter, page: PageRequest) -> Page[AuditLogItemView]:
        entries, total = self._repository.query(criteria, offset=page.offset, limit=page.size)
        page.ensure_in_range(total)
        actor_ids = {entry.actor_id for entry in entries if entry.actor_id is not None}
        names = self._user_names(actor_ids) if actor_ids else {}
        items = [
            AuditLogItemView(
                id=entry.id,
                workspace_id=entry.workspace_id,
                event_type=entry.event_type,
                actor_id=entry.actor_id,
                actor_name=names.get(entry.actor_id, "Usuario") if entry.actor_id else "Sistema",
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                ticket_id=entry.ticket_id,
                detail=entry.detail,
                integrity_hash=entry.integrity_hash,
                occurred_at=entry.occurred_at,
            )
            for entry in entries
        ]
        return Page(items=items, page=page.page, size=page.size, total=total)


class AuditEventHandler:
    """Suscriptor de DomainEvent que traduce cada evento de dominio en una AuditEntry inmutable."""

    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Session]] = SessionLocal,
        masker: IPiiMasker | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._masker = masker

    def _get_masker(self) -> IPiiMasker:
        if self._masker is None:
            self._masker = get_pii_masker()
        return self._masker

    def _mask_text(self, value: str | None) -> str | None:
        if not value:
            return value
        return self._get_masker().mask(value).text

    def __call__(self, event: DomainEvent) -> AuditEntry | None:
        entry = self.to_audit_entry(event)
        if entry is None:
            return None
        with self._session_factory() as session:
            SqlAlchemyAuditLogRepository(session).append(entry)
            session.commit()
        return entry

    def to_audit_entry(self, event: DomainEvent) -> AuditEntry | None:
        event_type = type(event).__name__
        workspace_id = getattr(event, "workspace_id", None)
        if workspace_id is None:
            return None

        actor_id: uuid.UUID | None = None
        entity_type = "workspace"
        entity_id: uuid.UUID | None = None
        ticket_id: uuid.UUID | None = getattr(event, "ticket_id", None)
        detail: dict[str, Any] = {}

        if event_type == "UserRegistered":
            actor_id = getattr(event, "user_id", None)
            entity_type = "user"
            entity_id = actor_id
            detail = {"role": str(getattr(event, "role", ""))}
        elif event_type == "UserAuthenticated":
            actor_id = getattr(event, "user_id", None)
            entity_type = "user"
            entity_id = actor_id
        elif event_type == "TicketRegistered":
            actor_id = getattr(event, "reporter_id", None)
            entity_type = "ticket"
            entity_id = ticket_id
            detail = {"has_evidence": bool(getattr(event, "has_evidence", False))}
        elif event_type == "TicketStatusChanged":
            actor_id = getattr(event, "changed_by", None)
            entity_type = "ticket"
            entity_id = ticket_id
            detail = {
                "previous_status": str(getattr(event, "previous_status", "")),
                "new_status": str(getattr(event, "new_status", "")),
                "reason": self._mask_text(getattr(event, "reason", None)),
            }
        elif event_type == "TicketClassificationCorrected":
            actor_id = getattr(event, "corrected_by", None)
            entity_type = "ticket"
            entity_id = ticket_id
            detail = {
                "previous_category": getattr(event, "previous_category", None),
                "new_category": getattr(event, "new_category", None),
                "previous_priority": str(getattr(event, "previous_priority", "")) if getattr(event, "previous_priority", None) else None,
                "new_priority": str(getattr(event, "new_priority", "")) if getattr(event, "new_priority", None) else None,
                "reason": self._mask_text(getattr(event, "reason", None)),
            }
        elif event_type == "TicketAssigned":
            actor_id = getattr(event, "assigned_by", None)
            entity_type = "ticket"
            entity_id = ticket_id
            detail = {
                "analyst_id": str(getattr(event, "analyst_id", "")),
                "previous_status": str(getattr(event, "previous_status", "")),
                "new_status": str(getattr(event, "new_status", "")),
            }
        elif event_type in {"TechnicalDocumentUploaded", "TechnicalDocumentVectorized", "TechnicalDocumentIngestionFailed"}:
            actor_id = getattr(event, "uploaded_by", None)
            entity_type = "technical_document"
            entity_id = getattr(event, "document_id", None)
            detail = {"job_id": str(getattr(event, "job_id", ""))}
            if hasattr(event, "chunk_count"):
                detail["chunk_count"] = getattr(event, "chunk_count")
            if hasattr(event, "reason"):
                detail["reason"] = self._mask_text(getattr(event, "reason", None))
        elif event_type == "LowConfidenceAlertRaised":
            entity_type = "ticket" if ticket_id else "knowledge_search"
            entity_id = ticket_id
            detail = {
                "best_score": getattr(event, "best_score", None),
                "similarity_threshold": getattr(event, "similarity_threshold", None),
                "fragments_retrieved": getattr(event, "fragments_retrieved", None),
            }
        elif event_type == "TriageCompleted":
            entity_type = "triage_diagnosis"
            entity_id = getattr(event, "diagnosis_id", None)
            detail = {
                "outcome": str(getattr(event, "outcome", "")),
                "confidence_level": getattr(event, "confidence_level", None),
                "best_score": getattr(event, "best_score", None),
                "route": str(getattr(event, "route", "")),
            }
            if getattr(event, "suggested_category", None) is not None:
                detail["suggested_category"] = str(getattr(event, "suggested_category"))
            if getattr(event, "suggested_priority", None) is not None:
                detail["suggested_priority"] = str(getattr(event, "suggested_priority"))
        elif event_type == "AiResolutionReviewed":
            actor_id = getattr(event, "reviewer_id", None)
            entity_type = "triage_diagnosis"
            entity_id = getattr(event, "diagnosis_id", None)
            detail = {
                "decision": str(getattr(event, "decision", "")),
                "previous_status": str(getattr(event, "previous_status", "")),
                "ai_outcome": str(getattr(event, "ai_outcome", "")),
                "resolves_ticket": bool(getattr(event, "resolves_ticket", False)),
                "note": self._mask_text(getattr(event, "note", None)),
            }
        else:
            for key, value in event.__dict__.items():
                if key in {"occurred_on", "workspace_id", "ticket_id"}:
                    continue
                if key in _TEXT_FIELDS and isinstance(value, str):
                    detail[key] = self._mask_text(value)
                elif isinstance(value, uuid.UUID):
                    detail[key] = str(value)
                else:
                    detail[key] = value

        return AuditEntry.record(
            workspace_id=workspace_id,
            event_type=event_type,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            ticket_id=ticket_id,
            detail=detail,
            occurred_at=event.occurred_on,
        )
