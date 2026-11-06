"""Implementación SQLAlchemy + pgvector del repositorio de documentos técnicos.

El repositorio no hace commit: la capa de aplicación controla la transacción.
"""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.knowledge.domain.enums import IngestionStatus
from app.knowledge.domain.repositories import ChunkSearchResult, ITechnicalDocumentRepository
from app.knowledge.domain.technical_document import KnowledgeChunk, TechnicalDocument
from app.knowledge.domain.value_objects import CitationMetadata, DocumentFileMetadata, VectorEmbedding
from app.knowledge.infrastructure.persistence.models import KbDocumentModel, KbKnowledgeChunkModel

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
        self._session.flush()
        self._save_chunks(document)
        return document

    def _save_chunks(self, document: TechnicalDocument) -> None:
        """Reemplaza los fragmentos guardados cuando el documento termina (VECTORIZED) o falla (FAILED)."""
        if document.status not in (IngestionStatus.VECTORIZED, IngestionStatus.FAILED):
            return
        self._session.execute(delete(KbKnowledgeChunkModel).where(KbKnowledgeChunkModel.document_id == document.id))
        if document.status is IngestionStatus.VECTORIZED:
            self._session.add_all(
                KbKnowledgeChunkModel(
                    id=chunk.id,
                    document_id=document.id,
                    workspace_id=document.workspace_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    source_file=chunk.citation.source_file,
                    page_number=chunk.citation.page_number,
                    paragraph_number=chunk.citation.paragraph_number,
                    section_title=chunk.citation.section_title,
                    embedding=list(chunk.embedding.values),
                )
                for chunk in document.chunks
            )
        self._session.flush()

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

    def find_ids_by_status(self, *statuses: IngestionStatus) -> list[uuid.UUID]:
        return list(
            self._session.scalars(
                select(KbDocumentModel.id)
                .where(KbDocumentModel.ingestion_status.in_(statuses))
                .order_by(KbDocumentModel.created_at)
            )
        )

    def search_similar_chunks(
        self, workspace_id: uuid.UUID, query: VectorEmbedding, *, top_k: int = 5
    ) -> list[ChunkSearchResult]:
        distance = KbKnowledgeChunkModel.embedding.cosine_distance(list(query.values))
        rows = self._session.execute(
            select(KbKnowledgeChunkModel, KbDocumentModel.title, distance.label("distance"))
            .join(KbDocumentModel, KbDocumentModel.id == KbKnowledgeChunkModel.document_id)
            .where(
                KbKnowledgeChunkModel.workspace_id == workspace_id,
                KbDocumentModel.ingestion_status == IngestionStatus.VECTORIZED,
            )
            .order_by(distance)
            .limit(top_k)
        ).all()
        return [
            ChunkSearchResult(
                chunk=self._chunk_to_domain(chunk), document_id=chunk.document_id, document_title=title, score=1 - dist
            )
            for chunk, title, dist in rows
        ]

    # ------------------------------------------------------------------ mapeo
    def _load_chunks(self, model: KbDocumentModel) -> list[KnowledgeChunk]:
        chunks = self._session.scalars(
            select(KbKnowledgeChunkModel)
            .where(KbKnowledgeChunkModel.document_id == model.id)
            .order_by(KbKnowledgeChunkModel.chunk_index)
        ).all()
        return [self._chunk_to_domain(c) for c in chunks]

    @staticmethod
    def _chunk_to_domain(model: KbKnowledgeChunkModel) -> KnowledgeChunk:
        return KnowledgeChunk(
            id=model.id,
            chunk_index=model.chunk_index,
            content=model.content,
            citation=CitationMetadata(
                source_file=model.source_file,
                page_number=model.page_number,
                paragraph_number=model.paragraph_number,
                section_title=model.section_title,
            ),
            embedding=VectorEmbedding(tuple(float(v) for v in model.embedding)),
        )

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
