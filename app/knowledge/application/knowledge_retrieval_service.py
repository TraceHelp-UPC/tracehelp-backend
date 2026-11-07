"""Búsqueda semántica en los manuales del workspace (US11, T30).

Es lo que Knowledge Management ofrece a los demás contextos: recibe la consulta ya anonimizada (SanitizedText con
sello), la convierte en vector con el mismo modelo de la ingesta y devuelve los fragmentos más parecidos.
"""
import uuid

from app.knowledge.application.ports import IEmbeddingGenerator
from app.knowledge.domain.repositories import ChunkSearchResult, ITechnicalDocumentRepository
from app.shared.domain.exceptions import DomainValidationError
from app.shared.domain.pii import SanitizedText

MAX_TOP_K = 20


class KnowledgeRetrievalService:
    def __init__(self, documents: ITechnicalDocumentRepository, embeddings: IEmbeddingGenerator) -> None:
        self._documents = documents
        self._embeddings = embeddings

    def search(self, workspace_id: uuid.UUID, query: SanitizedText, *, top_k: int) -> list[ChunkSearchResult]:
        """Top-k fragmentos de manuales VECTORIZED del workspace, ordenados por similitud coseno."""
        if not 1 <= top_k <= MAX_TOP_K:
            raise DomainValidationError(f"top_k debe estar entre 1 y {MAX_TOP_K}.")
        vector = self._embeddings.embed_query(query)  # el adaptador verifica el sello PII antes de enviar
        return self._documents.search_similar_chunks(workspace_id, vector, top_k=top_k)
