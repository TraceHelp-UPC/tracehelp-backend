"""Modelos ORM del contexto Smart Triage (tablas triage_*)."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.smart_triage.domain.diagnosis import DiagnosisStatus, SuggestedCategory, SuggestedPriority
from app.smart_triage.domain.grounding import ConfidenceLevel
from app.smart_triage.domain.triage_diagnosis import ReviewStatus


def _enum(enum_cls, name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=30,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda cls: [e.value for e in cls],
    )


class TriageDiagnosisModel(Base):
    __tablename__ = "triage_diagnoses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("iam_workspaces.id"), nullable=False, index=True)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("helpdesk_tickets.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    outcome: Mapped[DiagnosisStatus] = mapped_column(_enum(DiagnosisStatus, "diagnosis_outcome"), nullable=False)
    confidence_level: Mapped[ConfidenceLevel | None] = mapped_column(
        _enum(ConfidenceLevel, "confidence_level"), nullable=True
    )
    best_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    similarity_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    self_service_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[ReviewStatus] = mapped_column(_enum(ReviewStatus, "review_status"), nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    sources: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    suggested_category: Mapped[SuggestedCategory | None] = mapped_column(
        _enum(SuggestedCategory, "suggested_category"), nullable=True
    )
    suggested_priority: Mapped[SuggestedPriority | None] = mapped_column(
        _enum(SuggestedPriority, "suggested_priority"), nullable=True
    )
    outcome_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_legible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ocr_error_codes: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Revisión humana (HITL, T35)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("iam_users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_steps: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    manual_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
