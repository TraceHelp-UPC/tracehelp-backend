"""Modelos ORM del Bounded Context Analytics (tablas analytics_*)."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.analytics.domain.enums import AuditActionType
from app.core.database import Base


def _enum(enum_cls, name: str) -> Enum:
    return Enum(enum_cls, name=name, native_enum=False, length=50, create_constraint=True, validate_strings=True)


class AuditLogModel(Base):
    """Tabla inmutable (append-only) de trazabilidad y auditoría de IA (US15, US21, TS06)."""

    __tablename__ = "analytics_audit_logs"
    __table_args__ = (
        Index("ix_analytics_audit_logs_workspace_occurred", "workspace_id", "occurred_at"),
        Index("ix_analytics_audit_logs_ticket_id", "ticket_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("iam_workspaces.id"), nullable=False)
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("helpdesk_tickets.id", ondelete="CASCADE"), nullable=False)
    action_type: Mapped[AuditActionType] = mapped_column(_enum(AuditActionType, "audit_action_type"), nullable=False)
    consulted_sources: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    validator_analyst_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("iam_users.id"), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    integrity_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
