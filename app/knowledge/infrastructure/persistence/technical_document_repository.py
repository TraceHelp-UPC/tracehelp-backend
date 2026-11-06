"""Implementación SQLAlchemy del repositorio de documentos técnicos.

El repositorio no hace commit: la capa de aplicación controla la transacción.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge.domain.repositories import ITechnicalDocumentRepository
from app.knowledge.domain.technical_document import TechnicalDocument
from app.knowledge.domain.value_objects import DocumentFileMetadata
from app.knowledge.infrastructure.persistence.models import KbDocumentModel

_SCALAR_FIELDS = (
    "job_id",
    "workspace_id",
    "uploaded_by",
    "title",
    "storage_uri",
    "chunk_count",
    "error_message",
    "created_at",
    "updated_at",
    "processing_started_at",
    "vectorized_at",
)


class SqlAlchemyTechnicalDocumentRepository(ITechnicalDocumentRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, document: TechnicalDocument) -> TechnicalDocument:
        model = self._session.get(KbDocumentModel, document.id)
        if model is None:
            model = KbDocumentModel(id=document.id)
            self._session.add(model)
        for name in _SCALAR_FIELDS:
            setattr(model, name, getattr(document, name))
        model.ingestion_status = document.status
        model.file_name = document.file.file_name
        model.document_format = document.file.format
        model.file_size_bytes = document.file.size_bytes
        self._save_chunks(document)
        self._session.flush()
        return document

    def _save_chunks(self, document: TechnicalDocument) -> None:
        """Los fragmentos se guardan con el pipeline de ingesta (T23)."""

    def find_by_id(self, document_id: uuid.UUID, *, with_chunks: bool = False) -> TechnicalDocument | None:
        model = self._session.get(KbDocumentModel, document_id, populate_existing=True)
        return self._to_domain(model, with_chunks=with_chunks) if model else None

    def find_by_job_id(self, job_id: uuid.UUID) -> TechnicalDocument | None:
        model = self._session.scalars(
            select(KbDocumentModel).where(KbDocumentModel.job_id == job_id).execution_options(populate_existing=True)
        ).one_or_none()
        return self._to_domain(model) if model else None

    def list_by_workspace(self, workspace_id: uuid.UUID) -> list[TechnicalDocument]:
        models = self._session.scalars(
            select(KbDocumentModel)
            .where(KbDocumentModel.workspace_id == workspace_id)
            .order_by(KbDocumentModel.created_at.desc())
        ).all()
        return [self._to_domain(m) for m in models]

    def _load_chunks(self, model: KbDocumentModel) -> list:
        """Los fragmentos se leen con el pipeline de ingesta (T23)."""
        return []

    def _to_domain(self, model: KbDocumentModel, *, with_chunks: bool = False) -> TechnicalDocument:
        return TechnicalDocument(
            id=model.id,
            file=DocumentFileMetadata(
                file_name=model.file_name, format=model.document_format, size_bytes=model.file_size_bytes
            ),
            status=model.ingestion_status,
            chunks=self._load_chunks(model) if with_chunks else None,
            **{name: getattr(model, name) for name in _SCALAR_FIELDS},
        )
