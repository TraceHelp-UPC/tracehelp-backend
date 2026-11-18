"""Casos de uso de escritura del contexto Helpdesk."""
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.helpdesk.application import status_change_policy
from app.helpdesk.application.ports import IAnalystAvailabilityReader, IImageProcessor
from app.helpdesk.application.status_change_policy import Actor
from app.helpdesk.domain import state_machine
from app.helpdesk.domain.enums import ImpactLevel, TicketCategory, TicketPriority, TicketStatus
from app.helpdesk.domain.exceptions import (
    InvalidTicketDataError,
    InvalidTicketStateTransitionError,
    InvalidVisualEvidenceError,
    TicketNotFoundError,
    TicketStatusChangeForbiddenError,
)
from app.helpdesk.domain.repositories import ITicketRepository
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.domain.value_objects import MAX_EVIDENCE_BYTES, VisualEvidence
from app.iam.domain.permissions import Permission
from app.shared.infrastructure.event_bus import InMemoryEventBus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadedFile:
    file_name: str
    content: bytes


@dataclass(frozen=True)
class RegisterTicketCommand:
    workspace_id: uuid.UUID
    reporter_id: uuid.UUID
    title: str
    description: str
    impact_level: ImpactLevel
    affected_module: str | None = None
    screenshots: list[UploadedFile] = field(default_factory=list)


@dataclass(frozen=True)
class ChangeTicketStatusCommand:
    ticket_id: uuid.UUID
    actor: Actor
    target_status: TicketStatus
    reason: str | None = None


@dataclass(frozen=True)
class CorrectTicketClassificationCommand:
    ticket_id: uuid.UUID
    actor: Actor
    category: TicketCategory | None = None
    priority: TicketPriority | None = None
    reason: str | None = None


@dataclass(frozen=True)
class AssignTicketCommand:
    ticket_id: uuid.UUID
    actor: Actor
    analyst_id: uuid.UUID | None = None
    reason: str | None = None


class TicketCommandService:
    def __init__(
        self,
        session: Session,
        tickets: ITicketRepository,
        images: IImageProcessor,
        events: InMemoryEventBus,
        analysts: IAnalystAvailabilityReader | None = None,
    ) -> None:
        self._session = session
        self._tickets = tickets
        self._images = images
        self._events = events
        self._analysts = analysts

    def register(self, command: RegisterTicketCommand) -> Ticket:
        """Registra un incidente con texto y capturas opcionales (US10, TS04) y publica TicketRegistered."""
        evidences = []
        for upload in command.screenshots:
            if len(upload.content) > MAX_EVIDENCE_BYTES:
                raise InvalidVisualEvidenceError(
                    f"La imagen '{upload.file_name}' supera el tamaño máximo permitido de 10 MB."
                )
            image = self._images.process(upload.content, upload.file_name)
            evidences.append(VisualEvidence(file_name=image.file_name, mime_type=image.mime_type, content=image.content))

        ticket = Ticket.register(
            workspace_id=command.workspace_id,
            reporter_id=command.reporter_id,
            title=command.title,
            description=command.description,
            impact_level=command.impact_level,
            affected_module=command.affected_module,
            evidences=evidences,
        )
        self._tickets.save(ticket)
        self._session.commit()
        # Se publica después del commit para no notificar cambios que podrían revertirse
        self._events.publish_all(ticket.pull_events())
        return ticket

    def change_status(self, command: ChangeTicketStatusCommand) -> Ticket:
        """Cambia el estado de un ticket (TS04).

        Orden de validación: el ticket existe y es visible (404), el cambio existe en la máquina de estados (422)
        y el actor puede hacerlo (403). Publica TicketStatusChanged después del commit.
        """
        actor = command.actor
        ticket = self._tickets.find_by_id(command.ticket_id)
        # Un ticket de otro workspace, o uno ajeno para un colaborador, se trata como inexistente
        if (
            ticket is None
            or ticket.workspace_id != actor.workspace_id
            or (not actor.is_support_staff and ticket.reporter_id != actor.id)
        ):
            raise TicketNotFoundError("El ticket no existe.")

        state_machine.ensure_transition(ticket.status, command.target_status)
        status_change_policy.authorize(actor, ticket, command.target_status)

        # Al tomar un ticket sin responsable, queda asignado a quien lo toma
        assignee_id = None
        if command.target_status is TicketStatus.ASSIGNED_L1 and ticket.assigned_analyst_id is None:
            assignee_id = actor.id

        ticket.change_status(
            command.target_status, changed_by=actor.id, reason=command.reason, assignee_id=assignee_id
        )
        self._tickets.save(ticket)
        self._session.commit()
        self._events.publish_all(ticket.pull_events())
        return ticket

    def assign_ticket(self, command: AssignTicketCommand) -> Ticket:
        """Asigna un ticket a un analista disponible o al propio analista que lo toma (US24, T47)."""
        actor = command.actor
        if not (actor.can(Permission.TICKETS_MANAGE) or actor.can(Permission.IAM_ADMIN)):
            raise TicketStatusChangeForbiddenError("No tienes permiso para asignar tickets.")
        ticket = self._tickets.find_by_id(command.ticket_id)
        if ticket is None or ticket.workspace_id != actor.workspace_id:
            raise TicketNotFoundError("El ticket no existe.")

        target_analyst_id = command.analyst_id or actor.id
        if self._analysts is not None:
            candidate = self._analysts.get_candidate(target_analyst_id)
            if candidate is None or candidate.workspace_id != actor.workspace_id or not candidate.is_active:
                raise InvalidTicketDataError("El analista indicado no existe en este workspace.")
            if not candidate.is_support_staff:
                raise InvalidTicketDataError("Solo se pueden asignar tickets a analistas o especialistas de soporte.")
            if not candidate.is_available:
                raise InvalidTicketStateTransitionError(
                    f"El analista {candidate.full_name} se encuentra UNAVAILABLE y no puede recibir tickets."
                )

        reason = command.reason or "Asignado a soporte Nivel 1"
        if ticket.status is TicketStatus.ASSIGNED_L1:
            ticket.assigned_analyst_id = target_analyst_id
        else:
            ticket.change_status(
                TicketStatus.ASSIGNED_L1,
                changed_by=actor.id,
                reason=reason,
                assignee_id=target_analyst_id,
            )
        self._tickets.save(ticket)
        self._session.commit()
        self._events.publish_all(ticket.pull_events())
        return ticket

    def route_after_triage(
        self,
        ticket_id: uuid.UUID,
        target: TicketStatus,
        reason: str,
        *,
        suggested_category: TicketCategory | None = None,
        suggested_priority: TicketPriority | None = None,
    ) -> Ticket | None:
        """Mueve el ticket según el resultado del triaje automático (T28) y aplica la clasificación sugerida (T41).

        Si el ticket ya no está en OPEN (por ejemplo, un analista lo tomó a mano), se respeta ese cambio y no se mueve.
        """
        ticket = self._tickets.find_by_id(ticket_id)
        if ticket is None:
            logger.warning("El triaje terminó para un ticket inexistente: %s", ticket_id)
            return None
        if ticket.status is not TicketStatus.OPEN:
            logger.info("El ticket %s ya está en %s; el triaje no lo mueve", ticket.code, ticket.status.value)
            return None
        ticket.apply_triage_classification(
            suggested_category=suggested_category,
            suggested_priority=suggested_priority,
        )
        ticket.change_status(target, changed_by=None, reason=reason)
        self._tickets.save(ticket)
        self._session.commit()
        self._events.publish_all(ticket.pull_events())
        return ticket

    def correct_classification(self, command: CorrectTicketClassificationCommand) -> Ticket:
        """Establece o corrige la clasificación del ticket por el analista (US27, T42)."""
        actor = command.actor
        if not actor.can(Permission.TICKETS_MANAGE):
            raise TicketStatusChangeForbiddenError("Solo el equipo de soporte puede clasificar tickets.")
        ticket = self._tickets.find_by_id(command.ticket_id)
        if ticket is None or ticket.workspace_id != actor.workspace_id:
            raise TicketNotFoundError("El ticket no existe.")
        ticket.correct_classification(
            corrected_by=actor.id,
            category=command.category,
            priority=command.priority,
            reason=command.reason,
        )
        self._tickets.save(ticket)
        self._session.commit()
        self._events.publish_all(ticket.pull_events())
        return ticket

    def stage_resolution(
        self, ticket_id: uuid.UUID, actor: Actor, *, response_text: str, ai_generated: bool
    ) -> list:
        """Deja el ticket en RESOLVED con la respuesta para el colaborador como comentario visible (US15, T35).

        No hace commit: lo hace quien llama, junto con la revisión del diagnóstico, en una sola transacción.
        Aplica las mismas reglas que PATCH /status: el ticket debe ser del workspace del analista, estar asignado
        (ASSIGNED_L1) o escalado (ESCALATED_L2), y el rol debe poder resolverlo. Devuelve los eventos por publicar.
        """
        ticket = self._tickets.find_by_id(ticket_id)
        if ticket is None or ticket.workspace_id != actor.workspace_id:
            raise TicketNotFoundError("El ticket no existe.")
        if ticket.status is TicketStatus.PENDING_ASSIGNMENT:
            raise InvalidTicketStateTransitionError(
                f"Toma el ticket {ticket.code} (Atender) antes de responderlo."
            )
        state_machine.ensure_transition(ticket.status, TicketStatus.RESOLVED)
        status_change_policy.authorize(actor, ticket, TicketStatus.RESOLVED)

        ticket.add_comment(author_id=actor.id, content=response_text, is_ai_generated=ai_generated)
        reason = "Respuesta de la IA validada por el analista." if ai_generated else "Respuesta manual del analista."
        ticket.change_status(TicketStatus.RESOLVED, changed_by=actor.id, reason=reason)
        self._tickets.save(ticket)
        return ticket.pull_events()
