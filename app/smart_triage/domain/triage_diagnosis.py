"""Agregado raíz TriageDiagnosis del Bounded Context Smart Triage (US11, US15, TS07)."""
import uuid
from datetime import UTC, datetime

from app.shared.domain.aggregate_root import AggregateRoot
from app.smart_triage.domain.enums import ConfidenceLevel, ValidationStatus
from app.smart_triage.domain.events import (
    AiResolutionReviewed,
    LowConfidenceAlertTriggered,
    RagRecommendationGenerated,
)
from app.smart_triage.domain.exceptions import (
    InvalidTriageReviewError,
    TriageDiagnosisAlreadyReviewedError,
)
from app.smart_triage.domain.grounding_evaluation import GroundingEvaluationDomainService
from app.smart_triage.domain.value_objects import (
    ConfidenceScore,
    SimilarityThresholds,
    SourceCitation,
)


def _now() -> datetime:
    return datetime.now(UTC)


class TriageDiagnosis(AggregateRoot):
    """Gestiona el diagnóstico RAG, la evaluación de confianza y la validación humana HITL (US11, US15, TS07)."""

    def __init__(
        self,
        *,
        id: uuid.UUID,
        workspace_id: uuid.UUID,
        ticket_id: uuid.UUID,
        query_text: str,
        confidence_score: ConfidenceScore,
        confidence_level: ConfidenceLevel,
        has_sufficient_evidence: bool,
        is_low_confidence_alert: bool,
        suggested_text: str | None = None,
        final_approved_text: str | None = None,
        validation_status: ValidationStatus = ValidationStatus.PENDING,
        reviewer_id: uuid.UUID | None = None,
        citations: list[SourceCitation] | tuple[SourceCitation, ...] | None = None,
        created_at: datetime | None = None,
        reviewed_at: datetime | None = None,
    ) -> None:
        super().__init__()
        self.id = id
        self.workspace_id = workspace_id
        self.ticket_id = ticket_id
        self.query_text = query_text
        self.confidence_score = confidence_score
        self.confidence_level = confidence_level
        self.has_sufficient_evidence = has_sufficient_evidence
        self.is_low_confidence_alert = is_low_confidence_alert
        self.suggested_text = suggested_text
        self.final_approved_text = final_approved_text
        self.validation_status = validation_status
        self.reviewer_id = reviewer_id
        self.citations = list(citations or [])
        self.created_at = created_at or _now()
        self.reviewed_at = reviewed_at

    @classmethod
    def evaluate_and_create(
        cls,
        *,
        workspace_id: uuid.UUID,
        ticket_id: uuid.UUID,
        query_text: str,
        citations: list[SourceCitation] | None = None,
        synthesized_answer: str | None = None,
        thresholds: SimilarityThresholds | None = None,
    ) -> "TriageDiagnosis":
        """Evalúa los fragmentos recuperados contra el umbral (0.70) y crea el diagnóstico (US11)."""
        evaluator = GroundingEvaluationDomainService(thresholds=thresholds)
        evaluation = evaluator.evaluate(citations or [])

        if evaluation.has_sufficient_evidence:
            draft = (synthesized_answer or "").strip() or (
                "Se recomienda aplicar el procedimiento descrito en la documentación oficial citada."
            )
            diagnosis = cls(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                ticket_id=ticket_id,
                query_text=query_text,
                confidence_score=evaluation.confidence_score,
                confidence_level=evaluation.confidence_level,
                has_sufficient_evidence=True,
                is_low_confidence_alert=False,
                suggested_text=draft,
                citations=list(evaluation.qualified_citations),
            )
            diagnosis.record_event(
                RagRecommendationGenerated(
                    diagnosis_id=diagnosis.id,
                    ticket_id=ticket_id,
                    workspace_id=workspace_id,
                    confidence_score=evaluation.confidence_score.value,
                    consulted_sources=diagnosis.citations_as_dicts(),
                )
            )
            return diagnosis

        reason = (
            "No se encontraron fuentes relevantes en la base de conocimiento."
            if evaluation.confidence_level is ConfidenceLevel.INSUFFICIENT_EVIDENCE
            else "El nivel de confianza se encuentra por debajo del umbral mínimo establecido (0.70)."
        )
        diagnosis = cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            query_text=query_text,
            confidence_score=evaluation.confidence_score,
            confidence_level=evaluation.confidence_level,
            has_sufficient_evidence=False,
            is_low_confidence_alert=True,
            suggested_text=None,
            citations=list(citations or []),
        )
        diagnosis.record_event(
            LowConfidenceAlertTriggered(
                diagnosis_id=diagnosis.id,
                ticket_id=ticket_id,
                workspace_id=workspace_id,
                confidence_score=evaluation.confidence_score.value,
                reason=reason,
            )
        )
        return diagnosis

    def citations_as_dicts(self) -> list[dict]:
        return [
            {
                "source_file": c.source_file,
                "page_number": c.page_number,
                "paragraph_number": c.paragraph_number,
                "similarity_score": c.similarity_score,
            }
            for c in self.citations
        ]

    def _ensure_not_reviewed(self) -> None:
        if self.validation_status is not ValidationStatus.PENDING:
            raise TriageDiagnosisAlreadyReviewedError("El diagnóstico ya fue revisado previamente.")

    def approve_hitl(self, reviewer_id: uuid.UUID) -> None:
        """Aprueba sin cambios la recomendación generada por la IA (US15 Escenario 1)."""
        self._ensure_not_reviewed()
        if not self.suggested_text or not self.has_sufficient_evidence:
            raise InvalidTriageReviewError(
                "No se puede aprobar automáticamente un diagnóstico sin recomendación fundamentada."
            )
        self.validation_status = ValidationStatus.APPROVED
        self.final_approved_text = self.suggested_text
        self.reviewer_id = reviewer_id
        self.reviewed_at = _now()
        self.record_event(
            AiResolutionReviewed(
                diagnosis_id=self.id,
                ticket_id=self.ticket_id,
                workspace_id=self.workspace_id,
                reviewer_id=reviewer_id,
                action="APPROVE",
                final_text=self.final_approved_text,
                consulted_sources=self.citations_as_dicts(),
                confidence_score=self.confidence_score.value,
            )
        )

    def edit_and_approve_hitl(self, reviewer_id: uuid.UUID, edited_text: str) -> None:
        """Modifica el contenido sugerido y aprueba la versión corregida (US15 Escenario 2)."""
        self._ensure_not_reviewed()
        cleaned = (edited_text or "").strip()
        if not cleaned:
            raise InvalidTriageReviewError("El texto editado por el analista no puede estar vacío.")
        self.validation_status = ValidationStatus.EDITED
        self.final_approved_text = cleaned
        self.reviewer_id = reviewer_id
        self.reviewed_at = _now()
        self.record_event(
            AiResolutionReviewed(
                diagnosis_id=self.id,
                ticket_id=self.ticket_id,
                workspace_id=self.workspace_id,
                reviewer_id=reviewer_id,
                action="EDIT",
                final_text=self.final_approved_text,
                consulted_sources=self.citations_as_dicts(),
                confidence_score=self.confidence_score.value,
            )
        )

    def reject_hitl(self, reviewer_id: uuid.UUID, reason: str | None = None) -> None:
        """Rechaza la recomendación evitando que sea enviada al colaborador (US15 Escenario 3)."""
        self._ensure_not_reviewed()
        self.validation_status = ValidationStatus.REJECTED
        self.final_approved_text = None
        self.reviewer_id = reviewer_id
        self.reviewed_at = _now()
        self.record_event(
            AiResolutionReviewed(
                diagnosis_id=self.id,
                ticket_id=self.ticket_id,
                workspace_id=self.workspace_id,
                reviewer_id=reviewer_id,
                action="REJECT",
                final_text=None,
                consulted_sources=self.citations_as_dicts(),
                confidence_score=self.confidence_score.value,
            )
        )

    def provide_manual_resolution(self, reviewer_id: uuid.UUID, manual_text: str) -> None:
        """Registra una respuesta manual redactada por el analista cuando no hay recomendación IA (US15 Escenario 5)."""
        self._ensure_not_reviewed()
        cleaned = (manual_text or "").strip()
        if not cleaned:
            raise InvalidTriageReviewError("La respuesta manual no puede estar vacía.")
        self.validation_status = ValidationStatus.MANUAL_ONLY
        self.final_approved_text = cleaned
        self.reviewer_id = reviewer_id
        self.reviewed_at = _now()
        self.record_event(
            AiResolutionReviewed(
                diagnosis_id=self.id,
                ticket_id=self.ticket_id,
                workspace_id=self.workspace_id,
                reviewer_id=reviewer_id,
                action="MANUAL",
                final_text=self.final_approved_text,
                consulted_sources=[],
                confidence_score=self.confidence_score.value,
            )
        )
