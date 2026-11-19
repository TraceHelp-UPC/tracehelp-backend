"""Esquemas Pydantic de respuesta para el contexto Analytics (US15, T36; US21, T96)."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.analytics.application.audit_log_service import (
    AuditLogItemView,
    AuthorizingAnalystView,
    TicketAuditTraceView,
)
from app.analytics.application.ports import DiagnosisTraceSummary, TicketTraceSummary, TraceSourceItem
from app.analytics.domain.audit_entry import AuditIntegrityReport
from app.shared.domain.pagination import Page


class AuditLogEntryResponse(BaseModel):
    id: uuid.UUID
    seq: int | None = None
    workspace_id: uuid.UUID
    event_type: str
    actor_id: uuid.UUID | None
    actor_name: str
    entity_type: str
    entity_id: uuid.UUID | None
    ticket_id: uuid.UUID | None
    detail: dict[str, Any]
    integrity_hash: str
    previous_hash: str | None = None
    occurred_at: datetime

    @classmethod
    def from_view(cls, item: AuditLogItemView) -> "AuditLogEntryResponse":
        return cls(
            id=item.id,
            seq=item.seq,
            workspace_id=item.workspace_id,
            event_type=item.event_type,
            actor_id=item.actor_id,
            actor_name=item.actor_name,
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            ticket_id=item.ticket_id,
            detail=item.detail,
            integrity_hash=item.integrity_hash,
            previous_hash=item.previous_hash,
            occurred_at=item.occurred_at,
        )


class AuditLogPageResponse(BaseModel):
    items: list[AuditLogEntryResponse]
    page: int
    size: int
    total: int
    total_pages: int

    @classmethod
    def from_page(cls, page: Page[AuditLogItemView]) -> "AuditLogPageResponse":
        return cls(
            items=[AuditLogEntryResponse.from_view(i) for i in page.items],
            page=page.page,
            size=page.size,
            total=page.total,
            total_pages=page.total_pages,
        )


class AuditIntegrityVerificationResponse(BaseModel):
    entry_id: uuid.UUID
    seq: int | None
    valid: bool
    status: str
    hash_valid: bool
    chain_valid: bool
    stored_hash: str
    computed_hash: str
    previous_entry_id: uuid.UUID | None
    stored_previous_hash: str | None
    expected_previous_hash: str | None
    verified_at: datetime
    message: str

    @classmethod
    def from_report(cls, report: AuditIntegrityReport) -> "AuditIntegrityVerificationResponse":
        return cls(
            entry_id=report.entry_id,
            seq=report.seq,
            valid=report.valid,
            status=report.status.value,
            hash_valid=report.hash_valid,
            chain_valid=report.chain_valid,
            stored_hash=report.stored_hash,
            computed_hash=report.computed_hash,
            previous_entry_id=report.previous_entry_id,
            stored_previous_hash=report.stored_previous_hash,
            expected_previous_hash=report.expected_previous_hash,
            verified_at=report.verified_at,
            message=report.message,
        )


class TraceTicketResponse(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    status: str
    priority: str
    category: str | None
    reporter_id: uuid.UUID
    reporter_name: str
    assigned_analyst_id: uuid.UUID | None
    assigned_analyst_name: str | None
    created_at: datetime
    resolved_at: datetime | None

    @classmethod
    def from_summary(cls, summary: TicketTraceSummary) -> "TraceTicketResponse":
        return cls(
            id=summary.id,
            code=summary.code,
            title=summary.title,
            status=summary.status,
            priority=summary.priority,
            category=summary.category,
            reporter_id=summary.reporter_id,
            reporter_name=summary.reporter_name,
            assigned_analyst_id=summary.assigned_analyst_id,
            assigned_analyst_name=summary.assigned_analyst_name,
            created_at=summary.created_at,
            resolved_at=summary.resolved_at,
        )


class TraceDiagnosisResponse(BaseModel):
    id: uuid.UUID
    outcome: str
    confidence_level: str | None
    best_score: float | None
    similarity_threshold: float | None
    self_service_threshold: float | None
    model: str | None
    review_status: str

    @classmethod
    def from_summary(cls, summary: DiagnosisTraceSummary) -> "TraceDiagnosisResponse":
        return cls(
            id=summary.id,
            outcome=summary.outcome,
            confidence_level=summary.confidence_level,
            best_score=summary.best_score,
            similarity_threshold=summary.similarity_threshold,
            self_service_threshold=summary.self_service_threshold,
            model=summary.model,
            review_status=summary.review_status,
        )


class TraceSourceResponse(BaseModel):
    reference: str
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    citation: str
    similarity: float

    @classmethod
    def from_item(cls, item: TraceSourceItem) -> "TraceSourceResponse":
        return cls(
            reference=item.reference,
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            document_title=item.document_title,
            citation=item.citation,
            similarity=item.similarity,
        )


class AuthorizingAnalystResponse(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    decision: str
    reviewed_at: datetime | None

    @classmethod
    def from_view(cls, view: AuthorizingAnalystView) -> "AuthorizingAnalystResponse":
        return cls(
            id=view.id,
            name=view.name,
            role=view.role,
            decision=view.decision,
            reviewed_at=view.reviewed_at,
        )


class TicketAuditTraceResponse(BaseModel):
    ticket: TraceTicketResponse
    diagnosis: TraceDiagnosisResponse | None
    sources: list[TraceSourceResponse]
    authorizing_analyst: AuthorizingAnalystResponse | None
    events: list[AuditLogEntryResponse]
    total_events: int
    all_hashes_valid: bool

    @classmethod
    def from_view(cls, view: TicketAuditTraceView) -> "TicketAuditTraceResponse":
        return cls(
            ticket=TraceTicketResponse.from_summary(view.ticket),
            diagnosis=TraceDiagnosisResponse.from_summary(view.diagnosis) if view.diagnosis else None,
            sources=[TraceSourceResponse.from_item(s) for s in view.sources],
            authorizing_analyst=(
                AuthorizingAnalystResponse.from_view(view.authorizing_analyst)
                if view.authorizing_analyst
                else None
            ),
            events=[AuditLogEntryResponse.from_view(e) for e in view.events],
            total_events=view.total_events,
            all_hashes_valid=view.all_hashes_valid,
        )
