"""Revisión humana de la respuesta de la IA (HITL, US15, T35).

El analista aprueba, edita y aprueba, rechaza o responde manualmente el diagnóstico de un ticket. Cuando la
revisión entrega una respuesta final, el ticket pasa a RESOLVED en la misma transacción: o se guardan las dos
cosas, o ninguna. Después del commit se publican AiResolutionReviewed (auditoría, T36) y los eventos del ticket.
"""
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.iam.domain.permissions import Permission
from app.shared.domain.exceptions import DomainError, ResourceNotFoundError
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.ports import ITicketResolver, Reviewer
from app.smart_triage.domain.repositories import ITriageDiagnosisRepository
from app.smart_triage.domain.triage_diagnosis import ReviewDecision, TriageDiagnosis


class DiagnosisNotFoundError(ResourceNotFoundError):
    """El diagnóstico no existe o es de otro workspace (HTTP 404)."""


class HitlPermissionError(DomainError):
    """El usuario no puede validar respuestas de la IA (HTTP 403)."""


@dataclass(frozen=True)
class ReviewDiagnosisCommand:
    diagnosis_id: uuid.UUID
    reviewer: Reviewer
    decision: ReviewDecision
    summary: str | None = None  # EDIT_AND_APPROVE
    steps: tuple[str, ...] = ()  # EDIT_AND_APPROVE
    reason: str | None = None  # REJECT
    response: str | None = None  # MANUAL_RESPONSE


@dataclass(frozen=True)
class ReviewResult:
    diagnosis: TriageDiagnosis
    ticket_resolved: bool


class HitlReviewService:
    def __init__(
        self,
        *,
        session: Session,
        diagnoses: ITriageDiagnosisRepository,
        tickets: ITicketResolver,
        events: InMemoryEventBus,
    ) -> None:
        self._session = session
        self._diagnoses = diagnoses
        self._tickets = tickets
        self._events = events

    def review(self, command: ReviewDiagnosisCommand) -> ReviewResult:
        reviewer = command.reviewer
        if Permission.TRIAGE_VALIDATE_HITL.value not in reviewer.permissions:
            raise HitlPermissionError("Tu rol no puede validar respuestas de la IA (requiere triage:validate_hitl).")
        diagnosis = self._diagnoses.find_by_id(command.diagnosis_id)
        if diagnosis is None or diagnosis.workspace_id != reviewer.workspace_id:
            raise DiagnosisNotFoundError("El diagnóstico no existe.")

        try:
            self._apply(diagnosis, command)
            ticket_events: list = []
            if diagnosis.resolves_ticket:
                ticket_events = self._tickets.stage_resolution(
                    diagnosis.ticket_id,
                    reviewer,
                    response_text=diagnosis.final_response_text(),
                    ai_generated=command.decision is not ReviewDecision.MANUAL_RESPONSE,
                )
            self._diagnoses.save(diagnosis)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

        self._events.publish_all(diagnosis.pull_events())
        self._events.publish_all(ticket_events)
        return ReviewResult(diagnosis=diagnosis, ticket_resolved=diagnosis.resolves_ticket)

    @staticmethod
    def _apply(diagnosis: TriageDiagnosis, command: ReviewDiagnosisCommand) -> None:
        reviewer_id = command.reviewer.id
        match command.decision:
            case ReviewDecision.APPROVE:
                diagnosis.approve(reviewer_id)
            case ReviewDecision.EDIT_AND_APPROVE:
                diagnosis.edit_and_approve(reviewer_id, summary=command.summary or "", steps=command.steps)
            case ReviewDecision.REJECT:
                diagnosis.reject(reviewer_id, reason=command.reason or "")
            case ReviewDecision.MANUAL_RESPONSE:
                diagnosis.respond_manually(reviewer_id, response=command.response or "")
