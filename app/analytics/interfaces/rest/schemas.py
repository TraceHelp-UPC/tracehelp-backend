"""DTOs de respuesta del Bounded Context Analytics (bitácora de auditoría)."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.analytics.domain.audit_trail_entry import AuditTrailEntry


class AuditLogEntryResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    ticket_id: uuid.UUID
    action_type: str
    consulted_sources: list[dict]
    validator_analyst_id: uuid.UUID | None
    confidence_score: float | None
    details: str | None
    integrity_hash_sha256: str
    integrity_verified: bool
    occurred_at: datetime

    @classmethod
    def from_domain(cls, entry: AuditTrailEntry) -> "AuditLogEntryResponse":
        return cls(
            id=entry.id,
            workspace_id=entry.workspace_id,
            ticket_id=entry.ticket_id,
            action_type=entry.action_type.value,
            consulted_sources=list(entry.consulted_sources),
            validator_analyst_id=entry.validator_analyst_id,
            confidence_score=entry.confidence_score,
            details=entry.details,
            integrity_hash_sha256=entry.integrity_hash_sha256,
            integrity_verified=entry.verify_integrity(),
            occurred_at=entry.occurred_at,
        )


class PaginatedAuditLogResponse(BaseModel):
    items: list[AuditLogEntryResponse]
    total: int
    page: int
    page_size: int
