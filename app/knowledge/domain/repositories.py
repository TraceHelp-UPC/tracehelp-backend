"""Contratos de persistencia del contexto Knowledge Management."""
import uuid
from abc import ABC, abstractmethod

from app.knowledge.domain.technical_document import TechnicalDocument


class ITechnicalDocumentRepository(ABC):
    @abstractmethod
    def save(self, document: TechnicalDocument) -> TechnicalDocument:
        """Inserta o actualiza el documento. Si el documento trae fragmentos, reemplaza los guardados."""

    @abstractmethod
    def find_by_id(self, document_id: uuid.UUID, *, with_chunks: bool = False) -> TechnicalDocument | None:
        """Devuelve el documento o None si no existe."""

    @abstractmethod
    def find_by_job_id(self, job_id: uuid.UUID) -> TechnicalDocument | None:
        """Devuelve el documento asociado al trabajo de ingesta o None."""

    @abstractmethod
    def list_by_workspace(self, workspace_id: uuid.UUID) -> list[TechnicalDocument]:
        """Documentos del workspace, del más reciente al más antiguo (sin fragmentos)."""
