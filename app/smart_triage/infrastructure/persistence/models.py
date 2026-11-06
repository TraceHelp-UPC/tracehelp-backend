"""Modelos ORM del Bounded Context Smart Triage (tablas triage_*)."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.smart_triage.domain.enums import ConfidenceLevel, ValidationStatus


def _enum(enum_cls, name: str) -> Enum:
    return Enum(enum_cls, name=name, native_enum=False, length=40, create_constraint=True, validate_strings=True)


class TriageDiagnosisModel(Base):
    """Persistencia relacional del diagnóstico RAG y su validación HITL (US11, US15, TS07)."""

    __tablename__ = "triage_diagnoses"
    __table_args__ = (
        Index("ix_triage_diagnoses_ticket_id", "ticket_id", unique=True),
        Index("ix_triage_diagnoses_workspace_status", "workspace_id", "validation_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("iam_workspaces.id"), nullable=False)
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("helpdesk_tickets.id", ondelete="CASCADE"), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.0"))
    confidence_level: Mapped[ConfidenceLevel] = mapped_column(
        _enum(ConfidenceLevel, "confidence_level"), nullable=False
    )
    has_sufficient_evidence: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_low_confidence_alert: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    suggested_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_approved_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_status: Mapped[ValidationStatus] = mapped_column(
        _enum(ValidationStatus, "validation_status"), nullable=False
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("iam_users.id"), nullable=True)
    citations: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
