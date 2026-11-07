"""Adaptador hacia Knowledge Management (anticorruption layer).

Traduce los resultados de búsqueda de Knowledge a los value objects de Smart Triage, para que el dominio
de triaje no dependa de los modelos internos de otro contexto.
"""
import uuid

from app.knowledge.application.knowledge_retrieval_service import KnowledgeRetrievalService
from app.shared.domain.pii import SanitizedText
from app.smart_triage.application.ports import IKnowledgeRetriever
from app.smart_triage.domain.grounding import EvidenceCitation, EvidenceFragment


class KnowledgeContextRetriever(IKnowledgeRetriever):
    def __init__(self, retrieval: KnowledgeRetrievalService) -> None:
        self._retrieval = retrieval

    def retrieve(self, workspace_id: uuid.UUID, query: SanitizedText, *, top_k: int) -> list[EvidenceFragment]:
        results = self._retrieval.search(workspace_id, query, top_k=top_k)
        return [
            EvidenceFragment(
                chunk_id=r.chunk.id,
                document_id=r.document_id,
                document_title=r.document_title,
                content=r.chunk.content,
                citation=EvidenceCitation(
                    source_file=r.chunk.citation.source_file,
                    paragraph_number=r.chunk.citation.paragraph_number,
                    page_number=r.chunk.citation.page_number,
                    section_title=r.chunk.citation.section_title,
                ),
                similarity=round(max(-1.0, min(1.0, float(r.score))), 4),
            )
            for r in results
        ]
