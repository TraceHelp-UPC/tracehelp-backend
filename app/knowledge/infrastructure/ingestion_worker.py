"""Worker de ingesta en segundo plano (T23, DocumentIngestionConsumer).

Escucha TechnicalDocumentUploaded y procesa el manual en un hilo aparte, con su propia sesión de base de datos,
para que POST /documents responda 202 de inmediato. Al arrancar la API se reanudan los documentos que quedaron
PENDING o PROCESSING (por ejemplo, si Render apagó el servicio a mitad de una ingesta).
"""
import logging
import uuid
from concurrent.futures import Future, ThreadPoolExecutor

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.knowledge.application.document_ingestion_service import DocumentIngestionService
from app.knowledge.domain.enums import IngestionStatus
from app.knowledge.domain.events import TechnicalDocumentUploaded
from app.knowledge.infrastructure.embeddings.gemini_embedding_adapter import GeminiEmbeddingAdapter
from app.knowledge.infrastructure.parsing.pdf_markdown_parser import PdfMarkdownParserAdapter
from app.knowledge.infrastructure.persistence.document_storage import DatabaseDocumentStorage
from app.knowledge.infrastructure.persistence.technical_document_repository import (
    SqlAlchemyTechnicalDocumentRepository,
)
from app.shared.infrastructure.event_bus import event_bus
from app.shared.infrastructure.pii_masker import get_pii_masker

logger = logging.getLogger(__name__)


def build_ingestion_service(session) -> DocumentIngestionService:
    settings = get_settings()
    masker = get_pii_masker()
    return DocumentIngestionService(
        session=session,
        documents=SqlAlchemyTechnicalDocumentRepository(session),
        storage=DatabaseDocumentStorage(session),
        parser=PdfMarkdownParserAdapter(),
        masker=masker,
        embeddings=GeminiEmbeddingAdapter(
            api_key=settings.gemini_api_key,
            masker=masker,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        ),
        events=event_bus,
    )


class BackgroundIngestionWorker:
    def __init__(self, max_workers: int = 2, session_factory=SessionLocal, service_factory=build_ingestion_service) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="kb-ingestion")
        self._session_factory = session_factory
        self._service_factory = service_factory

    def on_document_uploaded(self, event: TechnicalDocumentUploaded) -> None:
        """Manejador del bus de eventos: encola el documento y regresa de inmediato."""
        self.enqueue(event.document_id)

    def enqueue(self, document_id: uuid.UUID) -> Future:
        return self._executor.submit(self._run, document_id)

    def _run(self, document_id: uuid.UUID) -> None:
        with self._session_factory() as session:
            try:
                self._service_factory(session).process(document_id)
            except Exception:  # noqa: BLE001 - el hilo nunca debe morir en silencio
                logger.exception("La ingesta del documento %s terminó con error", document_id)

    def resume_pending(self) -> int:
        """Vuelve a encolar los documentos PENDING y los PROCESSING interrumpidos. Devuelve cuántos encoló."""
        with self._session_factory() as session:
            documents = SqlAlchemyTechnicalDocumentRepository(session)
            ids = documents.find_ids_by_status(IngestionStatus.PENDING, IngestionStatus.PROCESSING)
            for document_id in ids:
                document = documents.find_by_id(document_id)
                if document.status is IngestionStatus.PROCESSING:
                    document.requeue()
                    documents.save(document)
            session.commit()
        for document_id in ids:
            self.enqueue(document_id)
        if ids:
            logger.info("Se reanudaron %s ingestas pendientes", len(ids))
        return len(ids)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


ingestion_worker = BackgroundIngestionWorker(max_workers=get_settings().ingestion_workers)
