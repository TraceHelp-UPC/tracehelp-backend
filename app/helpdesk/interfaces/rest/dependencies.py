"""Construcción de servicios de Helpdesk para los endpoints."""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.helpdesk.application.ticket_command_service import TicketCommandService
from app.helpdesk.infrastructure.image_processor import PillowImageProcessor
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.shared.infrastructure.event_bus import InMemoryEventBus, get_event_bus


def get_ticket_command_service(
    db: Session = Depends(get_db),
    bus: InMemoryEventBus = Depends(get_event_bus),
) -> TicketCommandService:
    return TicketCommandService(
        session=db, tickets=SqlAlchemyTicketRepository(db), images=PillowImageProcessor(), events=bus
    )
