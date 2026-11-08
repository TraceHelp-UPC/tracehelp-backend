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


def get_triage_analysis_service(
    retrieval: EvidenceRetrievalService = Depends(get_evidence_retrieval_service),
    generation: DiagnosisGenerationService = Depends(get_diagnosis_generation_service),
):
    from app.smart_triage.application.triage_analysis_service import TriageAnalysisService
    from app.smart_triage.infrastructure.ocr.tesseract_ocr_adapter import TesseractOcrAdapter

    return TriageAnalysisService(ocr=TesseractOcrAdapter(), retrieval=retrieval, generation=generation)


def build_hitl_review_service(session: Session, events: InMemoryEventBus):
    """Servicio de revisión HITL (T35); lo expone el endpoint de T39."""
    from app.smart_triage.application.hitl_review_service import HitlReviewService
    from app.smart_triage.infrastructure.helpdesk.helpdesk_ticket_resolver import HelpdeskTicketResolver
    from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
        SqlAlchemyTriageDiagnosisRepository,
    )

    return HitlReviewService(
        session=session,
        diagnoses=SqlAlchemyTriageDiagnosisRepository(session),
        tickets=HelpdeskTicketResolver(session, events),
        events=events,
    )


def get_diagnosis_query_service(db: Session = Depends(get_db)):
    from app.smart_triage.application.diagnosis_query_service import DiagnosisQueryService
    from app.smart_triage.infrastructure.helpdesk.helpdesk_ticket_reader import HelpdeskTicketReader
    from app.smart_triage.infrastructure.iam_user_names import IamUserNames
    from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
        SqlAlchemyTriageDiagnosisRepository,
    )

    return DiagnosisQueryService(
        diagnoses=SqlAlchemyTriageDiagnosisRepository(db), tickets=HelpdeskTicketReader(db), users=IamUserNames(db)
    )


def get_hitl_review_service(db: Session = Depends(get_db), bus: InMemoryEventBus = Depends(get_event_bus)):
    return build_hitl_review_service(db, bus)
