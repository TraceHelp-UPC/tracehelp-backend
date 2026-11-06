"""Pipeline de ingesta en segundo plano (T23, ProcessDocumentIngestionCommand).

PENDING -> PROCESSING -> extracción -> chunking -> anonimización -> embeddings -> VECTORIZED.
Si algo falla, el documento queda en FAILED con un motivo legible para el líder de TI.
"""
import logging
import uuid

from sqlalchemy.orm import Session

from app.knowledge.application.ports import (
    DocumentParsingError,
    EmbeddingProviderError,
    EmbeddingProviderNotConfiguredError,
    IDocumentParser,
    IDocumentStorage,
    IEmbeddingGenerator,
)
from app.knowledge.domain.chunking import DocumentChunkingDomainService
from app.knowledge.domain.enums import IngestionStatus
from app.knowledge.domain.repositories import ITechnicalDocumentRepository
from app.knowledge.domain.technical_document import TechnicalDocument
from app.shared.domain.exceptions import DomainError
from app.shared.domain.pii import IPiiMasker
from app.shared.infrastructure.event_bus import InMemoryEventBus

logger = logging.getLogger(__name__)

EMBEDDING_FAILURE = "El servicio de embeddings no respondió. Vuelve a cargar el manual en unos minutos."
NOT_CONFIGURED_FAILURE = "El servicio de embeddings no está configurado (falta GEMINI_API_KEY). Avisa al administrador."
UNEXPECTED_FAILURE = "Ocurrió un error inesperado al procesar el manual."
NO_TEXT_FAILURE = "El manual no tiene texto que se pueda indexar."


class DocumentIngestionService:
    def __init__(
        self,
        session: Session,
        documents: ITechnicalDocumentRepository,
        storage: IDocumentStorage,
        parser: IDocumentParser,
        masker: IPiiMasker,
        embeddings: IEmbeddingGenerator,
        events: InMemoryEventBus,
        chunker: DocumentChunkingDomainService | None = None,
    ) -> None:
        self._session = session
        self._documents = documents
        self._storage = storage
        self._parser = parser
        self._masker = masker
        self._embeddings = embeddings
        self._events = events
        self._chunker = chunker or DocumentChunkingDomainService()

    def process(self, document_id: uuid.UUID) -> TechnicalDocument | None:
        """Procesa un documento PENDING. Es idempotente: si ya está en otro estado, no hace nada."""
        document = self._documents.find_by_id(document_id)
        if document is None:
            logger.warning("Ingesta: el documento %s no existe", document_id)
            return None
        if document.status is not IngestionStatus.PENDING:
            logger.info("Ingesta: el documento %s ya está en %s", document_id, document.status.value)
            return document

        document.start_processing()
        self._documents.save(document)
        self._session.commit()

        try:
            self._vectorize(document)
        except Exception as exc:  # noqa: BLE001 - cualquier fallo deja el documento en FAILED con un motivo
            self._session.rollback()
            reason = self._failure_reason(exc)
            if isinstance(exc, (DomainError, EmbeddingProviderError)):
                logger.warning("Ingesta del documento %s falló: %s", document_id, exc)
            else:
                logger.exception("Error inesperado en la ingesta del documento %s", document_id)
            document = self._documents.find_by_id(document_id)
            document.mark_failed(reason)

        self._documents.save(document)
        self._session.commit()
        self._events.publish_all(document.pull_events())
        return document

    def _vectorize(self, document: TechnicalDocument) -> None:
        content = self._storage.load(document.storage_uri)
        paragraphs = self._parser.parse(content, document.file.format)
        chunks = self._chunker.chunk(paragraphs, source_file=document.file.file_name)
        if not chunks:
            raise DocumentParsingError(NO_TEXT_FAILURE)

        # Regla del equipo: ningún texto sale hacia Gemini sin pasar por el módulo PII (T27)
        sanitized = self._masker.mask_many([self._embedding_input(document, c.content, c.citation.section_title) for c in chunks])
        vectors = self._embeddings.embed_documents(sanitized)
        if len(vectors) != len(chunks):
            raise EmbeddingProviderError(f"Se esperaban {len(chunks)} vectores y llegaron {len(vectors)}.")
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk.attach_embedding(vector)
        document.complete_vectorization(chunks)

    @staticmethod
    def _embedding_input(document: TechnicalDocument, content: str, section: str | None) -> str:
        """El título del manual y la sección dan contexto al vector sin cambiar el texto guardado del fragmento."""
        header = f"{document.title} — {section}" if section else document.title
        return f"{header}\n\n{content}"

    @staticmethod
    def _failure_reason(exc: Exception) -> str:
        if isinstance(exc, DomainError):
            return exc.detail
        if isinstance(exc, EmbeddingProviderNotConfiguredError):
            return NOT_CONFIGURED_FAILURE
        if isinstance(exc, EmbeddingProviderError):
            return EMBEDDING_FAILURE
        return UNEXPECTED_FAILURE
