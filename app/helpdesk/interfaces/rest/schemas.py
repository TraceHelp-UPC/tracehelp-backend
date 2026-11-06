"""DTOs de respuesta del contexto Helpdesk."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.helpdesk.domain.enums import TicketStatus
from app.helpdesk.domain.ticket import MAX_REASON_LENGTH, Ticket


class EvidenceResponse(BaseModel):
    id: uuid.UUID
    file_name: str
    mime_type: str
    size_bytes: int


class TicketResponse(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    description: str
    affected_module: str | None
    impact_level: str
    status: str
    priority: str
    current_tier: str
    reporter_id: uuid.UUID
    assigned_analyst_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None
    evidences: list[EvidenceResponse]

    @classmethod
    def from_domain(cls, ticket: Ticket) -> "TicketResponse":
        return cls(
            id=ticket.id,
            code=ticket.code,
            title=ticket.title,
            description=ticket.description,
            affected_module=ticket.affected_module,
            impact_level=ticket.impact_level.value,
            status=ticket.status.value,
            priority=ticket.priority.value,
            current_tier=ticket.current_tier.value,
            reporter_id=ticket.reporter_id,
            assigned_analyst_id=ticket.assigned_analyst_id,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            resolved_at=ticket.resolved_at,
            closed_at=ticket.closed_at,
            evidences=[
                EvidenceResponse(id=e.id, file_name=e.file_name, mime_type=e.mime_type, size_bytes=e.size_bytes)
                for e in ticket.evidences
            ],
        )


class ChangeTicketStatusRequest(BaseModel):
    status: TicketStatus = Field(..., description="Nuevo estado del ticket", examples=["ASSIGNED_L1"])
    reason: str | None = Field(
        None, max_length=MAX_REASON_LENGTH, description="Motivo del cambio (opcional)", examples=["Tomo el ticket"]
    )


class AnalystAvailabilityRequest(BaseModel):
    availability: str = Field(..., description="Disponibilidad: AVAILABLE o UNAVAILABLE", examples=["UNAVAILABLE"])


class AnalystAvailabilityResponse(BaseModel):
    user_id: uuid.UUID
    availability_status: str
