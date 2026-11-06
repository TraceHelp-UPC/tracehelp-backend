"""DTOs de respuesta del contexto Knowledge Management."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.knowledge.domain.technical_document import TechnicalDocument


class IngestionJobResponse(BaseModel):
    """Respuesta 202 de la carga: el procesamiento continúa en segundo plano."""

    job_id: uuid.UUID
    document_id: uuid.UUID
    status: str = Field(..., examples=["PENDING"])
    status_url: str = Field(..., description="Ruta para consultar el avance", examples=["/api/v1/documents/jobs/..."])
    message: str

    @classmethod
    def from_domain(cls, document: TechnicalDocument, status_url: str) -> "IngestionJobResponse":
        return cls(
            job_id=document.job_id,
            document_id=document.id,
            status=document.status.value,
            status_url=status_url,
            message="El manual se recibió y se procesará en segundo plano.",
        )


class DocumentResponse(BaseModel):
    """Estado de un manual y su trabajo de ingesta."""

    document_id: uuid.UUID
    job_id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    file_name: str
    format: str = Field(..., examples=["PDF"])
    size_bytes: int
    status: str = Field(..., examples=["VECTORIZED"])
    chunk_count: int
    error_message: str | None
    uploaded_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    processing_started_at: datetime | None
    vectorized_at: datetime | None

    @classmethod
    def from_domain(cls, document: TechnicalDocument) -> "DocumentResponse":
        return cls(
            document_id=document.id,
            job_id=document.job_id,
            workspace_id=document.workspace_id,
            title=document.title,
            file_name=document.file.file_name,
            format=document.file.format.value,
            size_bytes=document.file.size_bytes,
            status=document.status.value,
            chunk_count=document.chunk_count,
            error_message=document.error_message,
            uploaded_by=document.uploaded_by,
            created_at=document.created_at,
            updated_at=document.updated_at,
            processing_started_at=document.processing_started_at,
            vectorized_at=document.vectorized_at,
        )
