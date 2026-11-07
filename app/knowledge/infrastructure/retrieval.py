"""Construcción del servicio de búsqueda en manuales con el adaptador de Gemini de producción."""
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.knowledge.application.knowledge_retrieval_service import KnowledgeRetrievalService
from app.knowledge.infrastructure.embeddings.gemini_embedding_adapter import GeminiEmbeddingAdapter
from app.knowledge.infrastructure.persistence.technical_document_repository import (
    SqlAlchemyTechnicalDocumentRepository,
)
from app.shared.infrastructure.pii_masker import get_pii_masker


def build_knowledge_retrieval_service(session: Session) -> KnowledgeRetrievalService:
    settings = get_settings()
    return KnowledgeRetrievalService(
        documents=SqlAlchemyTechnicalDocumentRepository(session),
        embeddings=GeminiEmbeddingAdapter(
            api_key=settings.gemini_api_key,
            masker=get_pii_masker(),
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        ),
    )
