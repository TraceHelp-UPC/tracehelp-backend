"""Eventos de dominio del contexto Knowledge Management."""
import uuid
from dataclasses import dataclass

from app.shared.domain.aggregate_root import DomainEvent


@dataclass(frozen=True, kw_only=True)
class TechnicalDocumentUploaded(DomainEvent):
    """Se emite al aceptar un manual. El worker de ingesta (T23) lo escucha para procesarlo en segundo plano."""

    document_id: uuid.UUID
    job_id: uuid.UUID
    workspace_id: uuid.UUID
    uploaded_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class TechnicalDocumentVectorized(DomainEvent):
    """Se emite cuando todos los fragmentos del manual tienen su vector. Smart Triage y Analytics lo usan."""

    document_id: uuid.UUID
    job_id: uuid.UUID
    workspace_id: uuid.UUID
    chunk_count: int


@dataclass(frozen=True, kw_only=True)
class TechnicalDocumentIngestionFailed(DomainEvent):
    """Se emite cuando el pipeline no pudo procesar el manual."""

    document_id: uuid.UUID
    job_id: uuid.UUID
    workspace_id: uuid.UUID
    reason: str
