"""Casos de uso de escritura del contexto Helpdesk."""
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.helpdesk.application.ports import IImageProcessor
from app.helpdesk.domain.enums import ImpactLevel
from app.helpdesk.domain.exceptions import InvalidVisualEvidenceError
from app.helpdesk.domain.repositories import ITicketRepository
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.domain.value_objects import MAX_EVIDENCE_BYTES, VisualEvidence
from app.shared.infrastructure.event_bus import InMemoryEventBus


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
