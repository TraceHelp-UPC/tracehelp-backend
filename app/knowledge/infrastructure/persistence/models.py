"""Modelos ORM del contexto Knowledge Management (tablas kb_*).

kb_documents guarda la cabecera y el estado de ingesta; kb_document_files guarda el archivo original.
Los fragmentos vectorizados (kb_knowledge_chunks) se agregan con el pipeline de ingesta (T23).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, LargeBinary, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.core.database import Base
from app.knowledge.domain.enums import DocumentFormat, IngestionStatus


def _enum(enum_cls, name: str) -> Enum:
    return Enum(enum_cls, name=name, native_enum=False, length=30, create_constraint=True, validate_strings=True)


class KbDocumentModel(Base):
    __tablename__ = "kb_documents"
    __table_args__ = (
        Index("ix_kb_documents_workspace_id_status", "workspace_id", "ingestion_status"),
        Index("ix_kb_documents_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("iam_workspaces.id"), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("iam_users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_format: Mapped[DocumentFormat] = mapped_column(_enum(DocumentFormat, "document_format"), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    ingestion_status: Mapped[IngestionStatus] = mapped_column(
        _enum(IngestionStatus, "ingestion_status"), nullable=False
    )
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vectorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KbDocumentFileModel(Base):
    """Archivo original del manual. Se guarda en la base porque el disco de Render (plan gratuito) es efímero."""

    __tablename__ = "kb_document_files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[bytes] = deferred(mapped_column(LargeBinary, nullable=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
