"""Construcción de servicios de Smart Triage para los endpoints."""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.knowledge.infrastructure.retrieval import build_knowledge_retrieval_service
from app.shared.infrastructure.event_bus import InMemoryEventBus, get_event_bus
from app.shared.infrastructure.pii_masker import get_pii_masker
from app.smart_triage.application.diagnosis_generation_service import DiagnosisGenerationService
from app.smart_triage.application.evidence_retrieval_service import EvidenceRetrievalService
from app.smart_triage.domain.grounding import GroundingThresholds
from app.smart_triage.infrastructure.knowledge.knowledge_context_retriever import KnowledgeContextRetriever
from app.smart_triage.infrastructure.llm.gemini_diagnosis_adapter import GeminiDiagnosisAdapter


def build_evidence_retrieval_service(session: Session, events: InMemoryEventBus) -> EvidenceRetrievalService:
    settings = get_settings()
    return EvidenceRetrievalService(
        retriever=KnowledgeContextRetriever(build_knowledge_retrieval_service(session)),
        masker=get_pii_masker(),
        events=events,
        thresholds=GroundingThresholds(
            similarity=settings.similarity_threshold, self_service=settings.self_service_threshold
        ),
        top_k=settings.retrieval_top_k,
    )


def get_evidence_retrieval_service(
    db: Session = Depends(get_db),
    bus: InMemoryEventBus = Depends(get_event_bus),
) -> EvidenceRetrievalService:
    return build_evidence_retrieval_service(db, bus)


def build_diagnosis_generation_service() -> DiagnosisGenerationService:
    settings = get_settings()
    masker = get_pii_masker()
    return DiagnosisGenerationService(
        generator=GeminiDiagnosisAdapter(api_key=settings.gemini_api_key, masker=masker, model=settings.llm_model),
        masker=masker,
    )


def get_diagnosis_generation_service() -> DiagnosisGenerationService:
    return build_diagnosis_generation_service()
