"""Casos de uso de escritura del contexto Helpdesk."""
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.helpdesk.application import status_change_policy
from app.helpdesk.application.ports import IImageProcessor
from app.helpdesk.application.status_change_policy import Actor
from app.helpdesk.domain import state_machine
from app.helpdesk.domain.enums import ImpactLevel, TicketStatus
from app.helpdesk.domain.exceptions import InvalidVisualEvidenceError, TicketNotFoundError
from app.helpdesk.domain.repositories import ITicketRepository
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.domain.value_objects import MAX_EVIDENCE_BYTES, VisualEvidence
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


class TicketCommandService:
    def __init__(
        self,
        session: Session,
        tickets: ITicketRepository,
        images: IImageProcessor,
        events: InMemoryEventBus,
    ) -> None:
        self._session = session
        self._tickets = tickets
        self._images = images
        self._events = events

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

    def route_after_triage(self, ticket_id: uuid.UUID, target: TicketStatus, reason: str) -> Ticket | None:
        """Mueve el ticket según el resultado del triaje automático (T28). Lo hace el sistema (changed_by=None).

        Si el ticket ya no está en OPEN (por ejemplo, un analista lo tomó a mano), se respeta ese cambio y no se mueve.
        """
        ticket = self._tickets.find_by_id(ticket_id)
        if ticket is None:
            logger.warning("El triaje terminó para un ticket inexistente: %s", ticket_id)
            return None
        if ticket.status is not TicketStatus.OPEN:
            logger.info("El ticket %s ya está en %s; el triaje no lo mueve", ticket.code, ticket.status.value)
            return None
        ticket.change_status(target, changed_by=None, reason=reason)
        self._tickets.save(ticket)
        self._session.commit()
        self._events.publish_all(ticket.pull_events())
        return ticket
