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
from app.smart_triage.domain.diagnosis import DiagnosisOutcome, DiagnosisStatus
from app.smart_triage.domain.events import TriageCompleted
from app.smart_triage.domain.grounding import ConfidenceLevel, EvidenceFragment, GroundingEvaluation


class ReviewStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"  # la IA respondió con evidencia media: un analista debe validarla (T35)
    SELF_SERVICE_PROPOSED = "SELF_SERVICE_PROPOSED"  # evidencia fuerte: se propuso al colaborador
    NOT_APPLICABLE = "NOT_APPLICABLE"  # no hay respuesta de la IA que revisar


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
    outcome_reason: str | None = None
    ocr: OcrSummary | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        AggregateRoot.__init__(self)

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
