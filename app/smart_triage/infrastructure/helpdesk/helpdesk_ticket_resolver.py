"""Resolución del ticket en Helpdesk desde la revisión HITL (anticorruption layer).

Usa la misma sesión que la revisión del diagnóstico para que ambas queden en una sola transacción.
"""
import uuid

from sqlalchemy.orm import Session

from app.helpdesk.application.status_change_policy import Actor
from app.helpdesk.application.ticket_command_service import TicketCommandService
from app.helpdesk.infrastructure.image_processor import PillowImageProcessor
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.ports import ITicketResolver, Reviewer


class HelpdeskTicketResolver(ITicketResolver):
    def __init__(self, session: Session, events: InMemoryEventBus) -> None:
        self._service = TicketCommandService(
            session=session,
            tickets=SqlAlchemyTicketRepository(session),
            images=PillowImageProcessor(),
            events=events,
        )

    def stage_resolution(
        self, ticket_id: uuid.UUID, reviewer: Reviewer, *, response_text: str, ai_generated: bool
    ) -> list:
        actor = Actor(id=reviewer.id, workspace_id=reviewer.workspace_id, permissions=reviewer.permissions)
        return self._service.stage_resolution(
            ticket_id, actor, response_text=response_text, ai_generated=ai_generated
        )
