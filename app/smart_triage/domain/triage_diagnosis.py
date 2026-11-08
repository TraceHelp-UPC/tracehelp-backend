"""Agregado TriageDiagnosis: el resultado del triaje automático de un ticket (TS02, T28).

Guarda lo que la IA encontró y propuso para que el analista lo revise (HITL, T35) y para la auditoría (T36).
Define también a dónde va el ticket después del triaje:
- respuesta con citas y evidencia fuerte (SELF_SERVICE)  -> se propone la solución al colaborador;
- cualquier otro caso (evidencia media, sin evidencia, IA sin respuesta válida o caída) -> cola de asignación.
"""
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.shared.domain.aggregate_root import AggregateRoot
from app.shared.domain.exceptions import DomainError, DomainValidationError
from app.smart_triage.domain.diagnosis import (
    MAX_STEP_CHARACTERS,
    MAX_STEPS,
    MAX_SUMMARY_CHARACTERS,
    DiagnosisOutcome,
    DiagnosisStatus,
    SuggestedCategory,
    SuggestedPriority,
)
from app.smart_triage.domain.events import AiResolutionReviewed, TriageCompleted
from app.smart_triage.domain.grounding import ConfidenceLevel, EvidenceFragment, GroundingEvaluation


MIN_MANUAL_RESPONSE_CHARACTERS = 10
MAX_MANUAL_RESPONSE_CHARACTERS = 4000
MIN_REJECTION_REASON_CHARACTERS = 5
MAX_REJECTION_REASON_CHARACTERS = 500


class ReviewStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"  # la IA respondió con evidencia media: un analista debe validarla (T35)
    SELF_SERVICE_PROPOSED = "SELF_SERVICE_PROPOSED"  # evidencia fuerte: se propuso al colaborador
    NOT_APPLICABLE = "NOT_APPLICABLE"  # no hay respuesta de la IA que revisar
    APPROVED = "APPROVED"  # el analista aprobó la respuesta de la IA tal cual
    EDITED_AND_APPROVED = "EDITED_AND_APPROVED"  # el analista corrigió la respuesta y la aprobó
    REJECTED = "REJECTED"  # el analista descartó la respuesta de la IA
    MANUAL_RESPONSE = "MANUAL_RESPONSE"  # el analista respondió con su propio texto


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    EDIT_AND_APPROVE = "EDIT_AND_APPROVE"
    REJECT = "REJECT"
    MANUAL_RESPONSE = "MANUAL_RESPONSE"


# Qué revisiones admite cada estado del diagnóstico
_ALLOWED: dict[ReviewDecision, frozenset[ReviewStatus]] = {
    ReviewDecision.APPROVE: frozenset({ReviewStatus.PENDING_REVIEW}),
    ReviewDecision.EDIT_AND_APPROVE: frozenset({ReviewStatus.PENDING_REVIEW}),
    ReviewDecision.REJECT: frozenset({ReviewStatus.PENDING_REVIEW}),
    ReviewDecision.MANUAL_RESPONSE: frozenset(
        {ReviewStatus.PENDING_REVIEW, ReviewStatus.REJECTED, ReviewStatus.NOT_APPLICABLE}
    ),
}


class DiagnosisAlreadyReviewedError(DomainError):
    """El diagnóstico ya fue revisado o no admite esa revisión (HTTP 409)."""


class InvalidReviewError(DomainValidationError):
    """Datos de la revisión no válidos: texto vacío, demasiado largo o sin motivo (HTTP 400)."""


class TicketRoute(StrEnum):
    """Estado del ticket que corresponde después del triaje (los nombres coinciden con TicketStatus de Helpdesk)."""

    SELF_SERVICE_PROPOSED = "SELF_SERVICE_PROPOSED"
    PENDING_ASSIGNMENT = "PENDING_ASSIGNMENT"


@dataclass(frozen=True)
class DiagnosisSource:
    """Fragmento citado en la respuesta, guardado tal como se mostró (la cita no cambia si el manual se borra)."""

    reference: str  # F1, F2...
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    citation: str
    similarity: float


@dataclass(frozen=True)
class OcrSummary:
    legible: bool
    error_codes: tuple[str, ...] = ()
    masked_text: str | None = None  # texto de las capturas ya anonimizado


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(eq=False)
class TriageDiagnosis(AggregateRoot):
    id: uuid.UUID
    workspace_id: uuid.UUID
    ticket_id: uuid.UUID
    outcome: DiagnosisStatus
    confidence_level: ConfidenceLevel | None
    best_score: float | None
    similarity_threshold: float | None
    self_service_threshold: float | None
    review_status: ReviewStatus
    summary: str | None = None
    steps: tuple[str, ...] = ()
    sources: tuple[DiagnosisSource, ...] = ()
    model: str | None = None
    suggested_category: SuggestedCategory | None = None
    suggested_priority: SuggestedPriority | None = None
    outcome_reason: str | None = None
    ocr: OcrSummary | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    final_summary: str | None = None  # versión aprobada o editada que ve el colaborador
    final_steps: tuple[str, ...] = ()
    manual_response: str | None = None
    review_note: str | None = None  # motivo del rechazo
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        AggregateRoot.__init__(self)

    @property
    def is_reviewed(self) -> bool:
        return self.reviewed_at is not None

    @property
    def resolves_ticket(self) -> bool:
        """La revisión entrega una respuesta final al colaborador (todas menos el rechazo)."""
        return self.review_status in (
            ReviewStatus.APPROVED,
            ReviewStatus.EDITED_AND_APPROVED,
            ReviewStatus.MANUAL_RESPONSE,
        )

    def can_review(self, decision: ReviewDecision) -> bool:
        return self.review_status in _ALLOWED[decision]

    def ensure_can_review(self, decision: ReviewDecision) -> None:
        if self.can_review(decision):
            return
        if self.review_status is ReviewStatus.SELF_SERVICE_PROPOSED:
            raise DiagnosisAlreadyReviewedError(
                "La solución se propuso al colaborador como autoservicio; la confirma él, no un analista."
            )
        if self.review_status is ReviewStatus.NOT_APPLICABLE:
            raise DiagnosisAlreadyReviewedError(
                "La IA no generó una respuesta para este ticket: solo se puede responder manualmente."
            )
        raise DiagnosisAlreadyReviewedError(f"El diagnóstico ya fue revisado ({self.review_status.value}).")

    def approve(self, reviewer_id: uuid.UUID) -> None:
        """El analista aprueba la respuesta de la IA tal como está."""
        self.ensure_can_review(ReviewDecision.APPROVE)
        self._finish_review(
            reviewer_id, ReviewStatus.APPROVED, ReviewDecision.APPROVE, summary=self.summary, steps=self.steps
        )

    def edit_and_approve(self, reviewer_id: uuid.UUID, *, summary: str, steps: list[str] | tuple[str, ...]) -> None:
        """El analista corrige el texto de la IA y lo aprueba. Se conserva la versión original para la auditoría."""
        self.ensure_can_review(ReviewDecision.EDIT_AND_APPROVE)
        summary = (summary or "").strip()
        clean_steps = tuple(s.strip() for s in steps if s and s.strip())
        if not summary:
            raise InvalidReviewError("El resumen editado no puede estar vacío.")
        if len(summary) > MAX_SUMMARY_CHARACTERS:
            raise InvalidReviewError(f"El resumen no puede superar los {MAX_SUMMARY_CHARACTERS} caracteres.")
        if not 1 <= len(clean_steps) <= MAX_STEPS:
            raise InvalidReviewError(f"La respuesta debe tener entre 1 y {MAX_STEPS} pasos.")
        if any(len(step) > MAX_STEP_CHARACTERS for step in clean_steps):
            raise InvalidReviewError(f"Cada paso puede tener como máximo {MAX_STEP_CHARACTERS} caracteres.")
        self._finish_review(
            reviewer_id,
            ReviewStatus.EDITED_AND_APPROVED,
            ReviewDecision.EDIT_AND_APPROVE,
            summary=summary,
            steps=clean_steps,
        )

    def reject(self, reviewer_id: uuid.UUID, *, reason: str) -> None:
        """El analista descarta la respuesta de la IA. El ticket sigue abierto con él."""
        self.ensure_can_review(ReviewDecision.REJECT)
        reason = (reason or "").strip()
        if len(reason) < MIN_REJECTION_REASON_CHARACTERS:
            raise InvalidReviewError("Indica por qué rechazas la respuesta de la IA.")
        if len(reason) > MAX_REJECTION_REASON_CHARACTERS:
            raise InvalidReviewError(f"El motivo no puede superar los {MAX_REJECTION_REASON_CHARACTERS} caracteres.")
        self.review_note = reason
        self._finish_review(reviewer_id, ReviewStatus.REJECTED, ReviewDecision.REJECT, note=reason)

    def respond_manually(self, reviewer_id: uuid.UUID, *, response: str) -> None:
        """El analista responde con su propio texto (la IA no respondió o su respuesta se rechazó)."""
        self.ensure_can_review(ReviewDecision.MANUAL_RESPONSE)
        response = (response or "").strip()
        if len(response) < MIN_MANUAL_RESPONSE_CHARACTERS:
            raise InvalidReviewError("Escribe la respuesta para el colaborador.")
        if len(response) > MAX_MANUAL_RESPONSE_CHARACTERS:
            raise InvalidReviewError(
                f"La respuesta no puede superar los {MAX_MANUAL_RESPONSE_CHARACTERS} caracteres."
            )
        self.manual_response = response
        self._finish_review(reviewer_id, ReviewStatus.MANUAL_RESPONSE, ReviewDecision.MANUAL_RESPONSE)

    def final_response_text(self) -> str | None:
        """Texto que se entrega al colaborador como respuesta del ticket, o None si la revisión no lo resuelve."""
        if self.review_status is ReviewStatus.MANUAL_RESPONSE:
            return self.manual_response
        if self.review_status not in (ReviewStatus.APPROVED, ReviewStatus.EDITED_AND_APPROVED):
            return None
        lines = [self.final_summary or "", ""]
        lines += [f"{i}. {step}" for i, step in enumerate(self.final_steps, start=1)]
        if self.sources:
            lines += ["", "Fuentes: " + "; ".join(f"[{s.reference}] {s.citation}" for s in self.sources)]
        return "\n".join(lines).strip()

    def _finish_review(
        self,
        reviewer_id: uuid.UUID,
        status: ReviewStatus,
        decision: ReviewDecision,
        *,
        summary: str | None = None,
        steps: tuple[str, ...] = (),
        note: str | None = None,
    ) -> None:
        previous = self.review_status
        if summary is not None:
            self.final_summary = summary
            self.final_steps = tuple(steps)
        self.review_status = status
        self.reviewed_by = reviewer_id
        self.reviewed_at = _now()
        self.updated_at = self.reviewed_at
        self.record_event(
            AiResolutionReviewed(
                diagnosis_id=self.id,
                ticket_id=self.ticket_id,
                workspace_id=self.workspace_id,
                reviewer_id=reviewer_id,
                decision=decision.value,
                previous_status=previous.value,
                ai_outcome=self.outcome.value,
                resolves_ticket=self.resolves_ticket,
                note=note,
            )
        )

    @property
    def route(self) -> TicketRoute:
        if self.review_status is ReviewStatus.SELF_SERVICE_PROPOSED:
            return TicketRoute.SELF_SERVICE_PROPOSED
        return TicketRoute.PENDING_ASSIGNMENT

    @classmethod
    def from_analysis(
        cls,
        *,
        workspace_id: uuid.UUID,
        ticket_id: uuid.UUID,
        evaluation: GroundingEvaluation,
        outcome: DiagnosisOutcome,
        ocr: OcrSummary | None,
    ) -> "TriageDiagnosis":
        """Registra el resultado de un análisis completo (evidencia evaluada y, si correspondía, respuesta de la IA)."""
        answered = outcome.answered and outcome.diagnosis is not None
        if answered and evaluation.level is ConfidenceLevel.SELF_SERVICE:
            review = ReviewStatus.SELF_SERVICE_PROPOSED
        elif answered:
            review = ReviewStatus.PENDING_REVIEW
        else:
            review = ReviewStatus.NOT_APPLICABLE

        sources: tuple[DiagnosisSource, ...] = ()
        if answered:
            numbers = {f.chunk_id: i for i, f in enumerate(evaluation.supporting, start=1)}
            sources = tuple(_source(f, numbers[f.chunk_id]) for f in outcome.diagnosis.sources)

        diagnosis = cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            outcome=outcome.status,
            confidence_level=evaluation.level,
            best_score=evaluation.best_score,
            similarity_threshold=evaluation.thresholds.similarity,
            self_service_threshold=evaluation.thresholds.self_service,
            review_status=review,
            summary=outcome.diagnosis.summary if answered else None,
            steps=outcome.diagnosis.steps if answered else (),
            sources=sources,
            model=outcome.diagnosis.model if answered else None,
            suggested_category=outcome.diagnosis.suggested_category if answered else None,
            suggested_priority=outcome.diagnosis.suggested_priority if answered else None,
            outcome_reason=outcome.reason,
            ocr=ocr,
        )
        diagnosis._record_completed()
        return diagnosis

    @classmethod
    def failed(
        cls, *, workspace_id: uuid.UUID, ticket_id: uuid.UUID, reason: str, ocr: OcrSummary | None = None
    ) -> "TriageDiagnosis":
        """El análisis no pudo completarse (proveedor de IA caído, captura inválida...): el ticket pasa a un analista."""
        diagnosis = cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            outcome=DiagnosisStatus.PROVIDER_ERROR,
            confidence_level=None,
            best_score=None,
            similarity_threshold=None,
            self_service_threshold=None,
            review_status=ReviewStatus.NOT_APPLICABLE,
            outcome_reason=reason,
            ocr=ocr,
        )
        diagnosis._record_completed()
        return diagnosis

    def _record_completed(self) -> None:
        self.record_event(
            TriageCompleted(
                diagnosis_id=self.id,
                ticket_id=self.ticket_id,
                workspace_id=self.workspace_id,
                outcome=self.outcome.value,
                confidence_level=self.confidence_level.value if self.confidence_level else None,
                best_score=self.best_score,
                route=self.route.value,
                suggested_category=self.suggested_category.value if self.suggested_category else None,
                suggested_priority=self.suggested_priority.value if self.suggested_priority else None,
            )
        )


def _source(fragment: EvidenceFragment, number: int) -> DiagnosisSource:
    return DiagnosisSource(
        reference=f"F{number}",
        chunk_id=fragment.chunk_id,
        document_id=fragment.document_id,
        document_title=fragment.document_title,
        citation=fragment.citation.label,
        similarity=fragment.similarity,
    )
