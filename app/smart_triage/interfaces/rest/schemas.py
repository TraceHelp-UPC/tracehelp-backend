"""DTOs de solicitud y respuesta del Bounded Context Smart Triage (US11, US15, TS07)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.smart_triage.domain.triage_diagnosis import TriageDiagnosis


class CitationResponse(BaseModel):
    source_file: str
    page_number: int
    paragraph_number: int
    similarity_score: float


class TriageDiagnosisResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    ticket_id: uuid.UUID
    query_text: str
    confidence_score: float
    confidence_level: str
    has_sufficient_evidence: bool
    is_low_confidence_alert: bool
    suggested_text: str | None
    final_approved_text: str | None
    validation_status: str
    reviewer_id: uuid.UUID | None
    citations: list[CitationResponse]
    created_at: datetime
    reviewed_at: datetime | None

    @classmethod
    def from_domain(cls, diagnosis: TriageDiagnosis) -> "TriageDiagnosisResponse":
        return cls(
            id=diagnosis.id,
            workspace_id=diagnosis.workspace_id,
            ticket_id=diagnosis.ticket_id,
            query_text=diagnosis.query_text,
            confidence_score=diagnosis.confidence_score.value,
            confidence_level=diagnosis.confidence_level.value,
            has_sufficient_evidence=diagnosis.has_sufficient_evidence,
            is_low_confidence_alert=diagnosis.is_low_confidence_alert,
            suggested_text=diagnosis.suggested_text,
            final_approved_text=diagnosis.final_approved_text,
            validation_status=diagnosis.validation_status.value,
            reviewer_id=diagnosis.reviewer_id,
            citations=[
                CitationResponse(
                    source_file=c.source_file,
                    page_number=c.page_number,
                    paragraph_number=c.paragraph_number,
                    similarity_score=c.similarity_score,
                )
                for c in diagnosis.citations
            ],
            created_at=diagnosis.created_at,
            reviewed_at=diagnosis.reviewed_at,
        )


class HumanReviewRequest(BaseModel):
    action: str = Field(..., description="Acción HITL: APPROVE, EDIT, REJECT o MANUAL", examples=["APPROVE"])
    edited_text: str | None = Field(
        None, description="Texto modificado o respuesta manual redactada por el analista"
    )
    reason: str | None = Field(None, description="Motivo del rechazo (opcional)")
