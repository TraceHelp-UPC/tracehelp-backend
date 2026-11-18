"""Construcción de servicios de Helpdesk para los endpoints."""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.helpdesk.application.ticket_command_service import TicketCommandService
from app.helpdesk.application.ticket_query_service import TicketQueryService
from app.helpdesk.infrastructure.iam_user_directory import IamUserDirectory
from app.helpdesk.infrastructure.image_processor import PillowImageProcessor
from app.helpdesk.infrastructure.persistence.ticket_read_model import SqlAlchemyTicketReadModel
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.shared.infrastructure.event_bus import InMemoryEventBus, get_event_bus


def get_ticket_command_service(
    db: Session = Depends(get_db),
    bus: InMemoryEventBus = Depends(get_event_bus),
) -> TicketCommandService:
    return TicketCommandService(
        session=db,
        tickets=SqlAlchemyTicketRepository(db),
        images=PillowImageProcessor(),
        events=bus,
        analysts=IamUserDirectory(db),
    )


def get_ticket_query_service(db: Session = Depends(get_db)) -> TicketQueryService:
    return TicketQueryService(
        read_model=SqlAlchemyTicketReadModel(db), tickets=SqlAlchemyTicketRepository(db), users=IamUserDirectory(db)
    )
