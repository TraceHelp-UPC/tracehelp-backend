"""Servicio de aplicación y manejador de eventos para la bitácora de auditoría (US15, T36; US21, T96)."""
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.analytics.application.ports import (
    DiagnosisTraceSummary,
    ITicketTraceReader,
    TicketTraceSummary,
    TraceSourceItem,
    UserIdentity,
)
from app.analytics.domain.audit_entry import AuditEntry, AuditIntegrityReport
from app.analytics.domain.exceptions import AuditEntryNotFoundError, TicketNotFoundError
from app.analytics.domain.repositories import AuditLogFilter, IAuditLogRepository
from app.analytics.infrastructure.persistence.audit_log_repository import SqlAlchemyAuditLogRepository
from app.core.database import SessionLocal
from app.shared.domain.aggregate_root import DomainEvent
from app.shared.domain.pagination import Page, PageRequest
from app.shared.domain.pii import IPiiMasker
from app.shared.infrastructure.pii_masker import get_pii_masker

# Campos de texto libre que se enmascaran con RegexSpacyPiiMasker antes de guardarse en detail
_TEXT_FIELDS = {"reason", "note"}

_APPROVING_DECISIONS = frozenset({"APPROVE", "EDIT_AND_APPROVE", "MANUAL_RESPONSE"})
_REVIEW_STATUS_TO_DECISION = {
    "APPROVED": "APPROVE",
    "EDITED_AND_APPROVED": "EDIT_AND_APPROVE",
    "REJECTED": "REJECT",
    "MANUAL_RESPONSE": "MANUAL_RESPONSE",
}


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
    seq: int | None = None
    previous_hash: str | None = None


@dataclass(frozen=True)
class AuthorizingAnalystView:
    id: uuid.UUID
    name: str
    role: str
    decision: str
    reviewed_at: datetime | None


@dataclass(frozen=True)
class TicketAuditTraceView:
    ticket: TicketTraceSummary
    diagnosis: DiagnosisTraceSummary | None
    sources: list[TraceSourceItem]
    authorizing_analyst: AuthorizingAnalystView | None
    events: list[AuditLogItemView]
    total_events: int
    all_hashes_valid: bool


class AuditLogService:
    """Servicio de consulta paginada, verificación de integridad y trazabilidad de la bitácora."""

    def __init__(
        self,
        repository: IAuditLogRepository,
        user_names: Callable[[set[uuid.UUID]], dict[uuid.UUID, str]] | None = None,
        trace_reader: ITicketTraceReader | None = None,
    ) -> None:
        self._repository = repository
        self._user_names = user_names or (lambda _: {})
        self._trace_reader = trace_reader

    def query(self, criteria: AuditLogFilter, page: PageRequest) -> Page[AuditLogItemView]:
        entries, total = self._repository.query(criteria, offset=page.offset, limit=page.size)
        page.ensure_in_range(total)
        actor_ids = {entry.actor_id for entry in entries if entry.actor_id is not None}
        names = self._user_names(actor_ids) if actor_ids else {}
        items = [self._to_item_view(entry, names) for entry in entries]
        return Page(items=items, page=page.page, size=page.size, total=total)

    def verify_entry(self, workspace_id: uuid.UUID, entry_id: uuid.UUID) -> AuditIntegrityReport:
        """Comprueba el hash SHA-256 propio y el encadenamiento con el registro predecesor en O(1)."""
        entry = self._repository.find_by_id(workspace_id, entry_id)
        if entry is None:
            raise AuditEntryNotFoundError("La entrada de auditoría solicitada no existe.")
        previous = (
            self._repository.find_previous(workspace_id, entry.seq) if entry.seq is not None else None
        )
        return AuditIntegrityReport.evaluate(entry, previous)

    def ticket_trace(self, workspace_id: uuid.UUID, ticket_id: uuid.UUID) -> TicketAuditTraceView:
        """Reconstruye la trazabilidad completa de un ticket (fuentes, analista autorizador y eventos)."""
        if self._trace_reader is None:
            raise RuntimeError("ITicketTraceReader no está configurado en AuditLogService.")

        snapshot = self._trace_reader.get_ticket_trace_snapshot(workspace_id, ticket_id)
        if snapshot is None:
            raise TicketNotFoundError("El ticket solicitado no existe.")

        entries = self._repository.list_for_ticket(workspace_id, ticket_id)

        user_ids: set[uuid.UUID] = {entry.actor_id for entry in entries if entry.actor_id is not None}
        if snapshot.diagnosis and snapshot.diagnosis.reviewed_by is not None:
            user_ids.add(snapshot.diagnosis.reviewed_by)

        identities = self._trace_reader.get_users_by_ids(user_ids) if user_ids else {}
        names = {uid: identity.full_name for uid, identity in identities.items()}
        missing = user_ids - set(names)
        if missing:
            names.update(self._user_names(missing))

        event_views = [self._to_item_view(entry, names) for entry in entries]
        authorizing_analyst = self._resolve_authorizing_analyst(entries, snapshot.diagnosis, identities, names)
        all_hashes_valid = all(entry.verify_integrity() for entry in entries)

        return TicketAuditTraceView(
            ticket=snapshot.ticket,
            diagnosis=snapshot.diagnosis,
            sources=list(snapshot.sources),
            authorizing_analyst=authorizing_analyst,
            events=event_views,
            total_events=len(event_views),
            all_hashes_valid=all_hashes_valid,
        )

    @staticmethod
    def _to_item_view(entry: AuditEntry, names: dict[uuid.UUID, str]) -> AuditLogItemView:
        return AuditLogItemView(
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
            seq=entry.seq,
            previous_hash=entry.previous_hash,
        )

    @staticmethod
    def _resolve_authorizing_analyst(
        entries: list[AuditEntry],
        diagnosis: DiagnosisTraceSummary | None,
        identities: dict[uuid.UUID, UserIdentity],
        names: dict[uuid.UUID, str],
    ) -> AuthorizingAnalystView | None:
        review_entries = [e for e in entries if e.event_type == "AiResolutionReviewed" and e.actor_id is not None]
        chosen: AuditEntry | None = None
        for entry in reversed(review_entries):
            if str(entry.detail.get("decision") or "") in _APPROVING_DECISIONS:
                chosen = entry
                break
        if chosen is None and review_entries:
            chosen = review_entries[-1]

        if chosen is not None and chosen.actor_id is not None:
            identity = identities.get(chosen.actor_id)
            return AuthorizingAnalystView(
                id=chosen.actor_id,
                name=identity.full_name if identity else names.get(chosen.actor_id, "Usuario"),
                role=identity.role if identity else "UNKNOWN",
                decision=str(chosen.detail.get("decision") or ""),
                reviewed_at=chosen.occurred_at,
            )

        if diagnosis is not None and diagnosis.reviewed_by is not None:
            identity = identities.get(diagnosis.reviewed_by)
            decision = _REVIEW_STATUS_TO_DECISION.get(diagnosis.review_status, diagnosis.review_status)
            return AuthorizingAnalystView(
                id=diagnosis.reviewed_by,
                name=identity.full_name if identity else names.get(diagnosis.reviewed_by, "Usuario"),
                role=identity.role if identity else "UNKNOWN",
                decision=decision,
                reviewed_at=diagnosis.reviewed_at,
            )

        return None


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
            persisted = SqlAlchemyAuditLogRepository(session).append(entry)
            session.commit()
        return persisted

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
            registered_by = getattr(event, "registered_by", None)
            entity_type = "user"
            entity_id = getattr(event, "user_id", None)
            actor_id = registered_by or entity_id
            detail = {
                "role": str(getattr(event, "role", "")),
                "specialist_group": getattr(event, "specialist_group", None),
                "source": "admin" if registered_by else "self",
            }
        elif event_type == "UserRoleChanged":
            actor_id = getattr(event, "changed_by", None)
            entity_type = "user"
            entity_id = getattr(event, "user_id", None)
            detail = {
                "previous_role": str(getattr(event, "previous_role", "")),
                "new_role": str(getattr(event, "new_role", "")),
            }
        elif event_type == "UserProfileUpdated":
            actor_id = getattr(event, "changed_by", None)
            entity_type = "user"
            entity_id = getattr(event, "user_id", None)
            detail = {"changes": getattr(event, "changes", {})}
        elif event_type in {"UserDeactivated", "UserReactivated"}:
            actor_id = getattr(event, "changed_by", None)
            entity_type = "user"
            entity_id = getattr(event, "user_id", None)
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
        elif event_type == "MessagePosted":
            # Rama explícita: nunca copia campos de más. El texto del mensaje no viaja en el evento ni se audita (D22)
            actor_id = getattr(event, "author_id", None)
            entity_type = "ticket_message"
            entity_id = getattr(event, "message_id", None)
            detail = {
                "is_internal_note": bool(getattr(event, "is_internal_note", False)),
                "author_is_reporter": bool(getattr(event, "author_is_reporter", False)),
                "ticket_status": str(getattr(event, "ticket_status", "")),
                "content_length": getattr(event, "content_length", None),
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
