"""Lectura de tickets de Helpdesk para el triaje (anticorruption layer).

Smart Triage solo lee los tickets; nunca los modifica. El cambio de estado lo hace Helpdesk al recibir
el evento TriageCompleted.
"""
import uuid

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.helpdesk.domain.enums import TicketStatus
from app.helpdesk.infrastructure.persistence.models import TicketModel
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.smart_triage.application.ports import IncidentToTriage, ITicketReader
from app.smart_triage.infrastructure.persistence.models import TriageDiagnosisModel


class HelpdeskTicketReader(ITicketReader):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, ticket_id: uuid.UUID) -> IncidentToTriage | None:
        ticket = SqlAlchemyTicketRepository(self._session).find_by_id(ticket_id)
        if ticket is None:
            return None
        return IncidentToTriage(
            ticket_id=ticket.id,
            workspace_id=ticket.workspace_id,
            title=ticket.title,
            description=ticket.description,
            affected_module=ticket.affected_module,
            screenshots=tuple(e.content for e in ticket.evidences),
        )

    def find_untriaged_open_ticket_ids(self) -> list[uuid.UUID]:
        has_diagnosis = exists().where(TriageDiagnosisModel.ticket_id == TicketModel.id)
        stmt = (
            select(TicketModel.id)
            .where(TicketModel.status == TicketStatus.OPEN, ~has_diagnosis)
            .order_by(TicketModel.created_at)
        )
        return list(self._session.scalars(stmt))
