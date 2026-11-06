"""Implementación SQLAlchemy del repositorio de diagnósticos de triaje."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.smart_triage.domain.repositories import ITriageDiagnosisRepository
from app.smart_triage.domain.triage_diagnosis import TriageDiagnosis
from app.smart_triage.domain.value_objects import ConfidenceScore, SourceCitation
from app.smart_triage.infrastructure.persistence.models import TriageDiagnosisModel


class SqlAlchemyTriageDiagnosisRepository(ITriageDiagnosisRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, diagnosis: TriageDiagnosis) -> TriageDiagnosis:
        model = self._session.get(TriageDiagnosisModel, diagnosis.id)
        if model is None:
            model = TriageDiagnosisModel(id=diagnosis.id)
            self._session.add(model)

        model.workspace_id = diagnosis.workspace_id
        model.ticket_id = diagnosis.ticket_id
        model.query_text = diagnosis.query_text
        model.confidence_score = diagnosis.confidence_score.value
        model.confidence_level = diagnosis.confidence_level
        model.has_sufficient_evidence = diagnosis.has_sufficient_evidence
        model.is_low_confidence_alert = diagnosis.is_low_confidence_alert
        model.suggested_text = diagnosis.suggested_text
        model.final_approved_text = diagnosis.final_approved_text
        model.validation_status = diagnosis.validation_status
        model.reviewer_id = diagnosis.reviewer_id
        model.citations = diagnosis.citations_as_dicts()
        model.created_at = diagnosis.created_at
        model.reviewed_at = diagnosis.reviewed_at

        self._session.flush()
        return diagnosis

    def find_by_id(self, diagnosis_id: uuid.UUID) -> TriageDiagnosis | None:
        model = self._session.get(TriageDiagnosisModel, diagnosis_id)
        return self._to_domain(model) if model else None

    def find_by_ticket_id(self, ticket_id: uuid.UUID) -> TriageDiagnosis | None:
        stmt = select(TriageDiagnosisModel).where(TriageDiagnosisModel.ticket_id == ticket_id)
        model = self._session.scalars(stmt).one_or_none()
        return self._to_domain(model) if model else None

    def _to_domain(self, model: TriageDiagnosisModel) -> TriageDiagnosis:
        citations = [
            SourceCitation(
                source_file=c["source_file"],
                page_number=int(c["page_number"]),
                paragraph_number=int(c["paragraph_number"]),
                similarity_score=float(c.get("similarity_score", 0.70)),
            )
            for c in (model.citations or [])
        ]
        return TriageDiagnosis(
            id=model.id,
            workspace_id=model.workspace_id,
            ticket_id=model.ticket_id,
            query_text=model.query_text,
            confidence_score=ConfidenceScore(model.confidence_score),
            confidence_level=model.confidence_level,
            has_sufficient_evidence=model.has_sufficient_evidence,
            is_low_confidence_alert=model.is_low_confidence_alert,
            suggested_text=model.suggested_text,
            final_approved_text=model.final_approved_text,
            validation_status=model.validation_status,
            reviewer_id=model.reviewer_id,
            citations=citations,
            created_at=model.created_at,
            reviewed_at=model.reviewed_at,
        )
