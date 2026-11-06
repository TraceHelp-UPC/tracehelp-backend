"""Servicio de consultas (Query Handler) del contexto Helpdesk (US13)."""
import uuid

from sqlalchemy.orm import Session

from app.helpdesk.domain.exceptions import TicketAccessForbiddenError, TicketNotFoundError
from app.helpdesk.domain.repositories import ITicketRepository
from app.helpdesk.domain.ticket import Ticket


class TicketQueryService:
    def __init__(self, session: Session, tickets: ITicketRepository) -> None:
        self._session = session
        self._tickets = tickets

    def get_reporter_history(self, workspace_id: uuid.UUID, reporter_id: uuid.UUID) -> list[Ticket]:
        """Obtiene el historial de tickets registrados por el colaborador solicitante (US13, T50, T51)."""
        return self._tickets.find_by_reporter(reporter_id=reporter_id, workspace_id=workspace_id)

    def get_ticket_details(
        self,
        workspace_id: uuid.UUID,
        ticket_id: uuid.UUID,
        requester_id: uuid.UUID,
        can_manage: bool = False,
    ) -> Ticket:
        """Obtiene el detalle de un ticket validando permisos de acceso (US13, T50, T51).

        Si el usuario no tiene permisos de gestión (tickets:manage) y no es el creador del ticket,
        se deniega el acceso con 403 Forbidden para evitar que un colaborador vea tickets de terceros.
        """
        ticket = self._tickets.find_by_id(ticket_id)
        if ticket is None or ticket.workspace_id != workspace_id:
            raise TicketNotFoundError("El incidente solicitado no existe.")

        if not can_manage and ticket.reporter_id != requester_id:
            raise TicketAccessForbiddenError("No tiene permiso para ver incidentes de otros colaboradores.")

        return ticket
