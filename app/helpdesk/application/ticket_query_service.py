"""Casos de uso de consulta de tickets (TS08): bandeja del analista, historial y detalle."""
import uuid
from dataclasses import dataclass

from app.helpdesk.application.status_change_policy import Actor
from app.helpdesk.application.ticket_queries import (
    SCOPE_STATUSES,
    EvidenceFile,
    ITicketReadModel,
    IUserDirectory,
    QueueScope,
    TicketOrder,
    TicketSearchCriteria,
    TicketSummary,
)
from app.helpdesk.domain.enums import TicketPriority, TicketStatus
from app.helpdesk.domain.exceptions import EvidenceNotFoundError, TicketAccessDeniedError, TicketNotFoundError
from app.helpdesk.domain.repositories import ITicketRepository
from app.helpdesk.domain.ticket import Ticket
from app.shared.domain.pagination import Page, PageRequest

MAX_SEARCH_LENGTH = 100


@dataclass(frozen=True)
class TicketListing:
    """Una página de resúmenes con los nombres de solicitantes y responsables."""

    page: Page[TicketSummary]
    names: dict[uuid.UUID, str]


@dataclass(frozen=True)
class TicketDetail:
    ticket: Ticket
    names: dict[uuid.UUID, str]
    include_internal_notes: bool


@dataclass(frozen=True)
class TicketStatusHistoryEntryView:
    id: uuid.UUID
    ticket_id: uuid.UUID
    previous_status: str
    new_status: str
    changed_by: uuid.UUID | None
    changed_by_name: str
    reason: str | None
    changed_at: object


@dataclass(frozen=True)
class TicketStatusHistoryView:
    ticket_id: uuid.UUID
    items: list[TicketStatusHistoryEntryView]


def _clean_search(search: str | None) -> str | None:
    search = (search or "").strip()
    return search[:MAX_SEARCH_LENGTH] or None


class TicketQueryService:
    def __init__(self, read_model: ITicketReadModel, tickets: ITicketRepository, users: IUserDirectory) -> None:
        self._read_model = read_model
        self._tickets = tickets
        self._users = users

    def queue(
        self,
        actor: Actor,
        *,
        scope: QueueScope = QueueScope.MINE,
        status: TicketStatus | None = None,
        priority: TicketPriority | None = None,
        search: str | None = None,
        page: PageRequest = PageRequest(),
    ) -> TicketListing:
        """Bandeja del analista (W-06), ordenada por prioridad y antigüedad. Requiere tickets:manage (lo valida la API)."""
        statuses = SCOPE_STATUSES[scope]
        if status is not None:
            statuses = statuses & {status}  # un estado fuera de la pestaña da una lista vacía
        criteria = TicketSearchCriteria(
            workspace_id=actor.workspace_id,
            statuses=statuses,
            priorities=frozenset({priority}) if priority else None,
            assigned_analyst_id=actor.id if scope is QueueScope.MINE else None,
            search=_clean_search(search),
            order=TicketOrder.PRIORITY,
        )
        return self._listing(criteria, page)

    def my_history(
        self,
        actor: Actor,
        *,
        status: TicketStatus | None = None,
        search: str | None = None,
        page: PageRequest = PageRequest(),
    ) -> TicketListing:
        """Tickets que reportó el usuario (W-04), del más reciente al más antiguo."""
        criteria = TicketSearchCriteria(
            workspace_id=actor.workspace_id,
            statuses=frozenset({status}) if status else None,
            reporter_id=actor.id,
            search=_clean_search(search),
            order=TicketOrder.RECENT,
        )
        return self._listing(criteria, page)

    def detail(self, actor: Actor, ticket_id: uuid.UUID) -> TicketDetail:
        """Detalle del ticket (W-05 / W-07). Lo ve quien lo reportó o el equipo de soporte del mismo workspace."""
        ticket = self._visible_ticket(actor, ticket_id)
        ids = {ticket.reporter_id, *(c.author_id for c in ticket.comments)}
        if ticket.assigned_analyst_id:
            ids.add(ticket.assigned_analyst_id)
        return TicketDetail(
            ticket=ticket,
            names=self._users.display_names(ids),
            include_internal_notes=actor.is_support_staff,
        )

    def evidence(self, actor: Actor, ticket_id: uuid.UUID, evidence_id: uuid.UUID) -> EvidenceFile:
        """Contenido de una captura, con las mismas reglas de acceso que el detalle."""
        self._visible_ticket(actor, ticket_id)
        evidence = self._read_model.get_evidence(ticket_id, evidence_id)
        if evidence is None:
            raise EvidenceNotFoundError("La captura no existe.")
        return evidence

    def history(self, actor: Actor, ticket_id: uuid.UUID) -> TicketStatusHistoryView:
        """Historial cronológico de cambios de estado del ticket (US14, T45)."""
        ticket = self._visible_ticket(actor, ticket_id)
        entries = sorted(ticket.status_history, key=lambda h: h.changed_at)
        actor_ids = {h.changed_by for h in entries if h.changed_by is not None}
        names = self._users.display_names(actor_ids) if actor_ids else {}
        items = [
            TicketStatusHistoryEntryView(
                id=h.id,
                ticket_id=ticket.id,
                previous_status=h.previous_status.value,
                new_status=h.new_status.value,
                changed_by=h.changed_by,
                changed_by_name=names.get(h.changed_by, "Usuario") if h.changed_by else "Sistema",
                reason=h.reason,
                changed_at=h.changed_at,
            )
            for h in entries
        ]
        return TicketStatusHistoryView(ticket_id=ticket.id, items=items)

    def _visible_ticket(self, actor: Actor, ticket_id: uuid.UUID) -> Ticket:
        ticket = self._tickets.find_by_id(ticket_id)
        if ticket is None or ticket.workspace_id != actor.workspace_id:
            raise TicketNotFoundError("El ticket no existe.")
        if not actor.is_support_staff and ticket.reporter_id != actor.id:
            raise TicketAccessDeniedError("No tienes acceso a este ticket: solo lo ven quien lo reportó y el equipo de soporte.")
        return ticket

    def _listing(self, criteria: TicketSearchCriteria, page: PageRequest) -> TicketListing:
        result = self._read_model.search(criteria, page)
        page.ensure_in_range(result.total)
        ids = {t.reporter_id for t in result.items} | {t.assigned_analyst_id for t in result.items if t.assigned_analyst_id}
        return TicketListing(page=result, names=self._users.display_names(ids))
