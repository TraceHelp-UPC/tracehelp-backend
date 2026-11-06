"""Agregado TechnicalDocument y su entidad interna KnowledgeChunk (TS01, US06)."""
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType

from app.knowledge.domain.enums import IngestionStatus
from app.knowledge.domain.events import (
    TechnicalDocumentIngestionFailed,
    TechnicalDocumentUploaded,
    TechnicalDocumentVectorized,
)
from app.knowledge.domain.exceptions import InvalidDocumentDataError, InvalidIngestionTransitionError
from app.knowledge.domain.value_objects import CitationMetadata, DocumentFileMetadata, VectorEmbedding
from app.shared.domain.aggregate_root import AggregateRoot

MAX_TITLE_LENGTH = 200
MAX_CHUNK_CHARS = 4000
MAX_ERROR_LENGTH = 500

S = IngestionStatus

# Ciclo de vida del pipeline de ingesta: PENDING -> PROCESSING -> VECTORIZED / FAILED.
# Un documento FAILED puede volver a PENDING para reintentar la ingesta.
ALLOWED_TRANSITIONS: MappingProxyType[IngestionStatus, frozenset[IngestionStatus]] = MappingProxyType(
    {
        S.PENDING: frozenset({S.PROCESSING, S.FAILED}),
        S.PROCESSING: frozenset({S.VECTORIZED, S.FAILED, S.PENDING}),
        S.VECTORIZED: frozenset(),
        S.FAILED: frozenset({S.PENDING}),
    }
)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class KnowledgeChunk:
    """Bloque de texto normalizado del manual, con su cita y (cuando se vectoriza) su embedding."""

    chunk_index: int
    content: str
    citation: CitationMetadata
    embedding: VectorEmbedding | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        self.content = (self.content or "").strip()
        if not self.content:
            raise InvalidDocumentDataError("El fragmento no puede estar vacío.")
        if len(self.content) > MAX_CHUNK_CHARS:
            raise InvalidDocumentDataError(f"El fragmento no puede superar los {MAX_CHUNK_CHARS} caracteres.")
        if self.chunk_index < 0:
            raise InvalidDocumentDataError("El índice del fragmento no puede ser negativo.")

    @property
    def is_vectorized(self) -> bool:
        return self.embedding is not None

    def attach_embedding(self, embedding: VectorEmbedding) -> None:
        self.embedding = embedding


class TechnicalDocument(AggregateRoot):
    """Manual técnico del workspace, desde la carga hasta su vectorización completa."""

    def __init__(
        self,
        *,
        id: uuid.UUID,
        job_id: uuid.UUID,
        workspace_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        title: str,
        file: DocumentFileMetadata,
        storage_uri: str,
        status: IngestionStatus,
        chunks: list[KnowledgeChunk] | None = None,
        chunk_count: int | None = None,
        error_message: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        processing_started_at: datetime | None = None,
        vectorized_at: datetime | None = None,
    ) -> None:
        super().__init__()
        self.id = id
        self.job_id = job_id
        self.workspace_id = workspace_id
        self.uploaded_by = uploaded_by
        self.title = title
        self.file = file
        self.storage_uri = storage_uri
        self.status = status
        self.chunks = list(chunks or [])
        # Al leer un documento no siempre se cargan sus fragmentos; chunk_count guarda cuántos tiene
        self.chunk_count = chunk_count if chunk_count is not None else len(self.chunks)
        self.error_message = error_message
        self.created_at = created_at or _now()
        self.updated_at = updated_at or self.created_at
        self.processing_started_at = processing_started_at
        self.vectorized_at = vectorized_at

    # ------------------------------------------------------------------ fábrica
    @classmethod
    def upload(
        cls,
        *,
        workspace_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        file: DocumentFileMetadata,
        storage_uri: str,
        title: str | None = None,
    ) -> "TechnicalDocument":
        """Registra un manual aceptado en estado PENDING y emite TechnicalDocumentUploaded (TS01)."""
        title = (title or "").strip() or file.stem
        if len(title) > MAX_TITLE_LENGTH:
            raise InvalidDocumentDataError(f"El título no puede superar los {MAX_TITLE_LENGTH} caracteres.")
        if not storage_uri or not storage_uri.strip():
            raise InvalidDocumentDataError("Falta la ubicación del archivo almacenado.")

        document = cls(
            id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            workspace_id=workspace_id,
            uploaded_by=uploaded_by,
            title=title,
            file=file,
            storage_uri=storage_uri,
            status=IngestionStatus.PENDING,
        )
        document.record_event(
            TechnicalDocumentUploaded(
                document_id=document.id,
                job_id=document.job_id,
                workspace_id=workspace_id,
                uploaded_by=uploaded_by,
            )
        )
        return document

    # ------------------------------------------------------------------ ciclo de vida
    @property
    def is_vectorized(self) -> bool:
        return self.status is IngestionStatus.VECTORIZED

    def _transition(self, target: IngestionStatus) -> None:
        if target not in ALLOWED_TRANSITIONS[self.status]:
            raise InvalidIngestionTransitionError(
                f"El documento no puede pasar de {self.status.value} a {target.value}."
            )
        self.status = target
        self.updated_at = _now()

    def start_processing(self) -> None:
        """El worker toma el documento: PENDING -> PROCESSING."""
        self._transition(IngestionStatus.PROCESSING)
        self.processing_started_at = self.updated_at
        self.error_message = None

    def complete_vectorization(self, chunks: list[KnowledgeChunk]) -> None:
        """PROCESSING -> VECTORIZED. Exige que todos los fragmentos tengan vector y cita."""
        if self.status is not IngestionStatus.PROCESSING:
            raise InvalidIngestionTransitionError(
                f"Solo se puede completar la vectorización de un documento en PROCESSING (está en {self.status.value})."
            )
        if not chunks:
            raise InvalidDocumentDataError("El documento no tiene texto que se pueda indexar.")
        pending = [c.chunk_index for c in chunks if not c.is_vectorized]
        if pending:
            raise InvalidDocumentDataError(f"Hay {len(pending)} fragmentos sin vector; no se puede marcar como VECTORIZED.")
        indexes = [c.chunk_index for c in chunks]
        if len(set(indexes)) != len(indexes):
            raise InvalidDocumentDataError("Hay fragmentos con el mismo índice.")

        self.chunks = sorted(chunks, key=lambda c: c.chunk_index)
        self.chunk_count = len(self.chunks)
        self._transition(IngestionStatus.VECTORIZED)
        self.vectorized_at = self.updated_at
        self.record_event(
            TechnicalDocumentVectorized(
                document_id=self.id, job_id=self.job_id, workspace_id=self.workspace_id, chunk_count=self.chunk_count
            )
        )

    def mark_failed(self, reason: str) -> None:
        """PENDING/PROCESSING -> FAILED con el motivo visible para el líder de TI."""
        reason = (reason or "").strip() or "Error desconocido durante la ingesta."
        self._transition(IngestionStatus.FAILED)
        self.error_message = reason[:MAX_ERROR_LENGTH]
        self.chunks = []
        self.chunk_count = 0
        self.record_event(
            TechnicalDocumentIngestionFailed(
                document_id=self.id, job_id=self.job_id, workspace_id=self.workspace_id, reason=self.error_message
            )
        )

    def requeue(self) -> None:
        """Vuelve a PENDING para reintentar: desde FAILED, o desde PROCESSING si el servidor se reinició a mitad."""
        self._transition(IngestionStatus.PENDING)
        self.processing_started_at = None
        self.error_message = None
