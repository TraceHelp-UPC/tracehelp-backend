"""Implementación SQLAlchemy del repositorio de diagnósticos. No hace commit."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.smart_triage.domain.repositories import ITriageDiagnosisRepository
from app.smart_triage.domain.triage_diagnosis import DiagnosisSource, OcrSummary, TriageDiagnosis
from app.smart_triage.infrastructure.persistence.models import TriageDiagnosisModel

_SCALARS = (
    "workspace_id",
    "ticket_id",
    "outcome",
    "confidence_level",
    "best_score",
    "similarity_threshold",
    "self_service_threshold",
    "review_status",
    "summary",
    "model",
    "outcome_reason",
    "created_at",
    "updated_at",
)


class SqlAlchemyTriageDiagnosisRepository(ITriageDiagnosisRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, diagnosis: TriageDiagnosis) -> TriageDiagnosis:
        model = self._session.get(TriageDiagnosisModel, diagnosis.id)
        if model is None:
            model = TriageDiagnosisModel(id=diagnosis.id)
            self._session.add(model)
        for name in _SCALARS:
            setattr(model, name, getattr(diagnosis, name))
        model.steps = list(diagnosis.steps)
        model.sources = [
            {
                "reference": s.reference,
                "chunk_id": str(s.chunk_id),
                "document_id": str(s.document_id),
                "document_title": s.document_title,
                "citation": s.citation,
                "similarity": s.similarity,
            }
            for s in diagnosis.sources
        ]
        model.ocr_legible = diagnosis.ocr.legible if diagnosis.ocr else None
        model.ocr_error_codes = list(diagnosis.ocr.error_codes) if diagnosis.ocr else []
        model.ocr_text = diagnosis.ocr.masked_text if diagnosis.ocr else None
        self._session.flush()
        return diagnosis

    def find_by_ticket_id(self, ticket_id: uuid.UUID) -> TriageDiagnosis | None:
        model = self._session.scalars(
            select(TriageDiagnosisModel).where(TriageDiagnosisModel.ticket_id == ticket_id)
        ).one_or_none()
        return self._to_domain(model) if model else None

    @staticmethod
    def _to_domain(model: TriageDiagnosisModel) -> TriageDiagnosis:
        ocr = None
        if model.ocr_legible is not None:
            ocr = OcrSummary(
                legible=model.ocr_legible, error_codes=tuple(model.ocr_error_codes or ()), masked_text=model.ocr_text
            )
        return TriageDiagnosis(
            id=model.id,
            steps=tuple(model.steps or ()),
            sources=tuple(
                DiagnosisSource(
                    reference=s["reference"],
                    chunk_id=uuid.UUID(s["chunk_id"]),
                    document_id=uuid.UUID(s["document_id"]),
                    document_title=s["document_title"],
                    citation=s["citation"],
                    similarity=s["similarity"],
                )
                for s in (model.sources or ())
            ),
            ocr=ocr,
            **{name: getattr(model, name) for name in _SCALARS},
        )
