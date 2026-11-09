"""Esquemas Pydantic de respuesta para el contexto Analytics (US15, T36)."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.analytics.application.audit_log_service import AuditLogItemView
from app.shared.domain.pagination import Page


class AuditLogEntryResponse(BaseModel):
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

    @classmethod
    def from_view(cls, item: AuditLogItemView) -> "AuditLogEntryResponse":
        return cls(
            id=item.id,
            workspace_id=item.workspace_id,
            event_type=item.event_type,
            actor_id=item.actor_id,
            actor_name=item.actor_name,
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            ticket_id=item.ticket_id,
            detail=item.detail,
            integrity_hash=item.integrity_hash,
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
