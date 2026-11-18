"""Modelos ORM del contexto Analytics (tablas analytics_*)."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLogModel(Base):
    """Bitácora de auditoría inmutable (US15, T36)."""

    __tablename__ = "analytics_audit_log"
    __table_args__ = (
        Index("ix_analytics_audit_log_workspace_occurred", "workspace_id", "occurred_at"),
        Index("ix_analytics_audit_log_event_type", "event_type"),
        Index("ix_analytics_audit_log_ticket_id", "ticket_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("iam_workspaces.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("iam_users.id"), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("helpdesk_tickets.id", ondelete="SET NULL"), nullable=True
    )
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    integrity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
