"""Casos de uso de escritura del contexto Knowledge Management."""
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.knowledge.application.ports import IDocumentStorage
from app.knowledge.domain.repositories import ITechnicalDocumentRepository
from app.knowledge.domain.technical_document import TechnicalDocument
from app.knowledge.domain.value_objects import DocumentFileMetadata
from app.shared.infrastructure.event_bus import InMemoryEventBus


@dataclass(frozen=True)
class UploadTechnicalDocumentCommand:
    workspace_id: uuid.UUID
    uploaded_by: uuid.UUID
    file_name: str
    content: bytes
    title: str | None = None


class KnowledgeCommandService:
    def __init__(
        self,
        session: Session,
        documents: ITechnicalDocumentRepository,
        storage: IDocumentStorage,
        events: InMemoryEventBus,
    ) -> None:
        self._session = session
        self._documents = documents
        self._storage = storage
        self._events = events

    def upload(self, command: UploadTechnicalDocumentCommand) -> TechnicalDocument:
        """Valida y guarda el manual en estado PENDING (TS01). El procesamiento ocurre en segundo plano (T23).

        Publica TechnicalDocumentUploaded después del commit para que el worker encuentre el documento guardado.
        """
        metadata = DocumentFileMetadata.from_upload(command.file_name, command.content)
        storage_uri = self._storage.save(
            file_name=metadata.file_name, mime_type=metadata.mime_type, content=command.content
        )
        document = TechnicalDocument.upload(
            workspace_id=command.workspace_id,
            uploaded_by=command.uploaded_by,
            file=metadata,
            storage_uri=storage_uri,
            title=command.title,
        )
        self._documents.save(document)
        self._session.commit()
        self._events.publish_all(document.pull_events())
        return document
