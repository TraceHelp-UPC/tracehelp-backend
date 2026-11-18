"""Consulta del diagnóstico de un ticket (TS07, T39).

- El equipo de soporte (tickets:manage) ve todo: propuesta de la IA, fuentes, puntajes, OCR y revisión.
- El colaborador que reportó el ticket solo lo ve cuando se le propuso como autoservicio.
"""
import uuid
from dataclasses import dataclass

from app.iam.domain.permissions import Permission
from app.shared.domain.exceptions import DomainError, ResourceNotFoundError
from app.smart_triage.application.ports import ITicketAccessReader, IUserNames, Reviewer, TicketAccess
from app.smart_triage.domain.repositories import ITriageDiagnosisRepository
from app.smart_triage.domain.triage_diagnosis import ReviewDecision, ReviewStatus, TriageDiagnosis


class DiagnosisAccessDeniedError(DomainError):
    """El usuario no puede ver el diagnóstico de este ticket (HTTP 403)."""


class TicketWithoutDiagnosisError(ResourceNotFoundError):
    """El ticket no existe o todavía no tiene diagnóstico (HTTP 404)."""


@dataclass(frozen=True)
class DiagnosisView:
    diagnosis: TriageDiagnosis
    ticket: TicketAccess
    names: dict[uuid.UUID, str]
    full_detail: bool  # False: vista del colaborador (sin puntajes, OCR ni datos de la revisión)
    allowed_actions: tuple[ReviewDecision, ...]


class DiagnosisQueryService:
    def __init__(self, *, diagnoses: ITriageDiagnosisRepository, tickets: ITicketAccessReader, users: IUserNames) -> None:
        self._diagnoses = diagnoses
        self._tickets = tickets
        self._users = users

    def for_ticket(self, viewer: Reviewer, ticket_id: uuid.UUID) -> DiagnosisView:
        ticket = self._tickets.find_access(ticket_id)
        if ticket is None or ticket.workspace_id != viewer.workspace_id:
            raise TicketWithoutDiagnosisError("El ticket no existe.")

        is_staff = Permission.TICKETS_MANAGE.value in viewer.permissions
        if not is_staff and ticket.reporter_id != viewer.id:
            raise DiagnosisAccessDeniedError("No tienes acceso a este ticket.")

        diagnosis = self._diagnoses.find_by_ticket_id(ticket_id)
        if diagnosis is None:
            raise TicketWithoutDiagnosisError(
                f"El ticket {ticket.code} todavía no tiene diagnóstico: el triaje automático está en curso."
            )
        if not is_staff and diagnosis.review_status is not ReviewStatus.SELF_SERVICE_PROPOSED:
            raise DiagnosisAccessDeniedError(
                "El diagnóstico de la IA solo lo revisa el equipo de soporte; recibirás la respuesta en el ticket."
            )

        can_review = Permission.TRIAGE_VALIDATE_HITL.value in viewer.permissions
        allowed = tuple(d for d in ReviewDecision if can_review and diagnosis.can_review(d))
        names = self._users.display_names({diagnosis.reviewed_by} - {None}) if is_staff else {}
        return DiagnosisView(
            diagnosis=diagnosis, ticket=ticket, names=names, full_detail=is_staff, allowed_actions=allowed
        )
