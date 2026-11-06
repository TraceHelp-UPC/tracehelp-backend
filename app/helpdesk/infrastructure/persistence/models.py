"""Modelos ORM del contexto Helpdesk (tablas helpdesk_*).

Las tablas de escalamientos, calificaciones y notificaciones se agregan en el Sprint 2 (US17, US18, US19).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Identity, Index, Integer, LargeBinary, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from app.core.database import Base
from app.helpdesk.domain.enums import ImpactLevel, SupportTier, TicketPriority, TicketStatus


def _enum(enum_cls, name: str) -> Enum:
    return Enum(enum_cls, name=name, native_enum=False, length=30, create_constraint=True, validate_strings=True)


class TicketModel(Base):
    __tablename__ = "helpdesk_tickets"
    __table_args__ = (
        Index("ix_helpdesk_tickets_workspace_id_status", "workspace_id", "status"),
        Index("ix_helpdesk_tickets_assigned_analyst_id", "assigned_analyst_id"),
        Index("ix_helpdesk_tickets_reporter_id", "reporter_id"),
        Index("ix_helpdesk_tickets_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    ticket_number: Mapped[int] = mapped_column(Integer, Identity(start=1), unique=True, nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("iam_workspaces.id"), nullable=False)
    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("iam_users.id"), nullable=False)
    assigned_analyst_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("iam_users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    affected_module: Mapped[str | None] = mapped_column(String(100), nullable=True)
    impact_level: Mapped[ImpactLevel] = mapped_column(_enum(ImpactLevel, "impact_level"), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(_enum(TicketStatus, "ticket_status"), nullable=False)
    priority: Mapped[TicketPriority] = mapped_column(_enum(TicketPriority, "ticket_priority"), nullable=False)
    current_tier: Mapped[SupportTier] = mapped_column(_enum(SupportTier, "support_tier"), nullable=False)
    external_itsm_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    evidences: Mapped[list["TicketEvidenceModel"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketEvidenceModel.uploaded_at", lazy="selectin"
    )
    comments: Mapped[list["TicketCommentModel"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketCommentModel.created_at", lazy="selectin"
    )
    status_history: Mapped[list["TicketStatusHistoryModel"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketStatusHistoryModel.changed_at",
        lazy="selectin",
    )


class TicketEvidenceModel(Base):
    __tablename__ = "helpdesk_ticket_evidences"
    __table_args__ = (Index("ix_helpdesk_ticket_evidences_ticket_id", "ticket_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("helpdesk_tickets.id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_data: Mapped[bytes] = deferred(mapped_column(LargeBinary, nullable=False))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    ticket: Mapped[TicketModel] = relationship(back_populates="evidences")


class TicketCommentModel(Base):
    __tablename__ = "helpdesk_ticket_comments"
    __table_args__ = (Index("ix_helpdesk_ticket_comments_ticket_id", "ticket_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("helpdesk_tickets.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("iam_users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_internal_note: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    ticket: Mapped[TicketModel] = relationship(back_populates="comments")


class TicketStatusHistoryModel(Base):
    __tablename__ = "helpdesk_ticket_status_history"
    __table_args__ = (
        Index("ix_helpdesk_status_history_ticket_id", "ticket_id"),
        Index("ix_helpdesk_status_history_changed_at", "changed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("helpdesk_tickets.id", ondelete="CASCADE"), nullable=False)
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("iam_users.id"), nullable=True)
    previous_status: Mapped[TicketStatus] = mapped_column(_enum(TicketStatus, "previous_ticket_status"), nullable=False)
    new_status: Mapped[TicketStatus] = mapped_column(_enum(TicketStatus, "new_ticket_status"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    ticket: Mapped[TicketModel] = relationship(back_populates="status_history")
