"""Pruebas unitarias de la consulta de historial de tickets y detalles (US13, T50, T51)."""
import uuid
import pytest

from app.helpdesk.application.ticket_query_service import TicketQueryService
from app.helpdesk.domain.enums import ImpactLevel, SupportTier, TicketPriority, TicketStatus
from app.helpdesk.domain.exceptions import TicketAccessForbiddenError, TicketNotFoundError
from app.helpdesk.domain.repositories import ITicketRepository
from app.helpdesk.domain.ticket import Ticket


class InMemoryTicketRepository(ITicketRepository):
    def __init__(self, tickets: list[Ticket] | None = None) -> None:
        self._tickets = {t.id: t for t in (tickets or [])}

    def save(self, ticket: Ticket) -> Ticket:
        self._tickets[ticket.id] = ticket
        return ticket

    def find_by_id(self, ticket_id: uuid.UUID) -> Ticket | None:
        return self._tickets.get(ticket_id)

    def find_by_reporter(self, reporter_id: uuid.UUID, workspace_id: uuid.UUID) -> list[Ticket]:
        return [
            t for t in self._tickets.values()
            if t.reporter_id == reporter_id and t.workspace_id == workspace_id
        ]


def _create_test_ticket(workspace_id: uuid.UUID, reporter_id: uuid.UUID, title: str = "Test") -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        reporter_id=reporter_id,
        title=title,
        description="Descripción del problema",
        impact_level=ImpactLevel.MEDIUM,
        affected_module=None,
        status=TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
        current_tier=SupportTier.SELF_SERVICE,
    )


def test_collaborator_can_get_my_history():
    workspace_id = uuid.uuid4()
    reporter_id = uuid.uuid4()
    other_reporter_id = uuid.uuid4()

    t1 = _create_test_ticket(workspace_id, reporter_id, "Ticket 1")
    t2 = _create_test_ticket(workspace_id, reporter_id, "Ticket 2")
    t3 = _create_test_ticket(workspace_id, other_reporter_id, "Ticket ajeno")

    repo = InMemoryTicketRepository([t1, t2, t3])
    service = TicketQueryService(session=None, tickets=repo)

    history = service.get_reporter_history(workspace_id, reporter_id)

    assert len(history) == 2
    assert t1 in history
    assert t2 in history
    assert t3 not in history


def test_collaborator_empty_history():
    workspace_id = uuid.uuid4()
    reporter_id = uuid.uuid4()

    repo = InMemoryTicketRepository([])
    service = TicketQueryService(session=None, tickets=repo)

    history = service.get_reporter_history(workspace_id, reporter_id)

    assert history == []


def test_collaborator_forbidden_from_viewing_other_collaborator_ticket():
    workspace_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    intruder_id = uuid.uuid4()

    ticket = _create_test_ticket(workspace_id, owner_id, "Ticket privado")
    repo = InMemoryTicketRepository([ticket])
    service = TicketQueryService(session=None, tickets=repo)

    with pytest.raises(TicketAccessForbiddenError):
        service.get_ticket_details(
            workspace_id=workspace_id,
            ticket_id=ticket.id,
            requester_id=intruder_id,
            can_manage=False,
        )


def test_collaborator_can_view_own_ticket():
    workspace_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    ticket = _create_test_ticket(workspace_id, owner_id, "Mi Ticket")
    repo = InMemoryTicketRepository([ticket])
    service = TicketQueryService(session=None, tickets=repo)

    result = service.get_ticket_details(
        workspace_id=workspace_id,
        ticket_id=ticket.id,
        requester_id=owner_id,
        can_manage=False,
    )

    assert result.id == ticket.id
    assert result.title == "Mi Ticket"


def test_analyst_with_manage_permission_can_view_any_ticket():
    workspace_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    analyst_id = uuid.uuid4()

    ticket = _create_test_ticket(workspace_id, owner_id, "Ticket reporte")
    repo = InMemoryTicketRepository([ticket])
    service = TicketQueryService(session=None, tickets=repo)

    result = service.get_ticket_details(
        workspace_id=workspace_id,
        ticket_id=ticket.id,
        requester_id=analyst_id,
        can_manage=True,
    )

    assert result.id == ticket.id


def test_nonexistent_ticket_raises_not_found():
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()

    repo = InMemoryTicketRepository([])
    service = TicketQueryService(session=None, tickets=repo)

    with pytest.raises(TicketNotFoundError):
        service.get_ticket_details(
            workspace_id=workspace_id,
            ticket_id=uuid.uuid4(),
            requester_id=user_id,
            can_manage=False,
        )
