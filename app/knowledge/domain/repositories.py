"""Contratos de persistencia del contexto Knowledge Management."""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.knowledge.domain.technical_document import KnowledgeChunk, TechnicalDocument
from app.knowledge.domain.value_objects import VectorEmbedding


@dataclass(frozen=True)
class ChunkSearchResult:
    """Fragmento recuperado por similitud coseno (0 a 1) con el documento al que pertenece."""

    chunk: KnowledgeChunk
    document_id: uuid.UUID
    document_title: str
    score: float


class ITechnicalDocumentRepository(ABC):
    @abstractmethod
    def save(self, document: TechnicalDocument) -> TechnicalDocument:
        """Inserta o actualiza el documento. Al quedar VECTORIZED guarda sus fragmentos; al quedar FAILED los borra."""

    @abstractmethod
    def find_by_id(self, document_id: uuid.UUID, *, with_chunks: bool = False) -> TechnicalDocument | None:
        """Devuelve el documento o None si no existe."""

    @abstractmethod
    def find_by_job_id(self, job_id: uuid.UUID) -> TechnicalDocument | None:
        """Devuelve el documento asociado al trabajo de ingesta o None."""

    @abstractmethod
    def list_by_workspace(self, workspace_id: uuid.UUID) -> list[TechnicalDocument]:
        """Documentos del workspace, del más reciente al más antiguo (sin fragmentos)."""

    @abstractmethod
    def find_ids_by_status(self, *statuses) -> list[uuid.UUID]:
        """Documentos en alguno de los estados indicados (para reanudar ingestas tras un reinicio)."""

    @abstractmethod
    def search_similar_chunks(
        self, workspace_id: uuid.UUID, query: VectorEmbedding, *, top_k: int = 5
    ) -> list[ChunkSearchResult]:
        """Fragmentos más parecidos del workspace (solo de documentos VECTORIZED), del más al menos similar.

        La evaluación contra los umbrales 0.70 y 0.85 la hace Smart Triage (T30).
        """
