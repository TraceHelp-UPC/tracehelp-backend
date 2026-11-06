"""Casos de uso de lectura del contexto Knowledge Management."""
import uuid

from app.knowledge.domain.exceptions import DocumentNotFoundError
from app.knowledge.domain.repositories import ITechnicalDocumentRepository
from app.knowledge.domain.technical_document import TechnicalDocument


class KnowledgeQueryService:
    def __init__(self, documents: ITechnicalDocumentRepository) -> None:
        self._documents = documents

    def get_ingestion_job(self, *, job_id: uuid.UUID, workspace_id: uuid.UUID) -> TechnicalDocument:
        """Estado del trabajo de ingesta. Un trabajo de otro workspace se trata como inexistente."""
        document = self._documents.find_by_job_id(job_id)
        if document is None or document.workspace_id != workspace_id:
            raise DocumentNotFoundError("El trabajo de ingesta no existe.")
        return document

    def list_documents(self, workspace_id: uuid.UUID) -> list[TechnicalDocument]:
        return self._documents.list_by_workspace(workspace_id)
