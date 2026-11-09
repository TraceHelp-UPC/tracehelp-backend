"""DTOs de respuesta del contexto Helpdesk."""
import base64
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.helpdesk.application.ticket_queries import EvidenceFile, TicketSummary
from app.helpdesk.application.ticket_query_service import (
    TicketDetail,
    TicketListing,
    TicketStatusHistoryEntryView,
    TicketStatusHistoryView,
)
from app.helpdesk.domain.enums import TicketCategory, TicketPriority, TicketStatus
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
    category: str | None = None
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
            category=ticket.category.value if ticket.category else None,
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


class CorrectTicketClassificationRequest(BaseModel):
    category: str | None = Field(
        None,
        description="Categoría técnica del catálogo: Red/VPN, Correo, Accesos, Hardware, Software u Otro",
        examples=["Red/VPN"],
    )
    priority: TicketPriority | None = Field(
        None, description="Prioridad del ticket: LOW, MEDIUM, HIGH o CRITICAL", examples=["HIGH"]
    )
    reason: str | None = Field(
        None, max_length=MAX_REASON_LENGTH, description="Motivo de la corrección", examples=["Falla de red corporativa"]
    )


class AssignTicketRequest(BaseModel):
    analyst_id: uuid.UUID | None = Field(
        None,
        description="ID del analista disponible a quien asignar el ticket (si se omite, se asigna al analista autenticado)",
    )
    reason: str | None = Field(
        None,
        max_length=MAX_REASON_LENGTH,
        description="Motivo de la asignación",
        examples=["Asignado a analista disponible"],
    )


class TicketSummaryResponse(BaseModel):
    """Fila de las bandejas W-04 y W-06 (sin descripción ni capturas)."""

    id: uuid.UUID
    code: str = Field(..., examples=["TK-0042"])
    title: str
    status: str
    priority: str
    category: str | None = None
    impact_level: str
    current_tier: str
    affected_module: str | None
    reporter_id: uuid.UUID
    reporter_name: str | None
    assigned_analyst_id: uuid.UUID | None
    assigned_analyst_name: str | None
    evidence_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_summary(cls, t: TicketSummary, names: dict[uuid.UUID, str]) -> "TicketSummaryResponse":
        return cls(
            id=t.id,
            code=t.code,
            title=t.title,
            status=t.status.value,
            priority=t.priority.value,
            category=t.category,
            impact_level=t.impact_level,
            current_tier=t.current_tier,
            affected_module=t.affected_module,
            reporter_id=t.reporter_id,
            reporter_name=names.get(t.reporter_id),
            assigned_analyst_id=t.assigned_analyst_id,
            assigned_analyst_name=names.get(t.assigned_analyst_id) if t.assigned_analyst_id else None,
            evidence_count=t.evidence_count,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )


class TicketPageResponse(BaseModel):
    items: list[TicketSummaryResponse]
    page: int = Field(..., examples=[1])
    size: int = Field(..., examples=[20])
    total: int = Field(..., description="Total de tickets que cumplen los filtros", examples=[57])
    total_pages: int = Field(..., examples=[3])

    @classmethod
    def from_listing(cls, listing: TicketListing) -> "TicketPageResponse":
        page = listing.page
        return cls(
            items=[TicketSummaryResponse.from_summary(t, listing.names) for t in page.items],
            page=page.page,
            size=page.size,
            total=page.total,
            total_pages=page.total_pages,
        )


class CommentResponse(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    author_name: str | None
    content: str
    is_ai_generated: bool
    is_internal_note: bool
    created_at: datetime


class TicketDetailResponse(TicketResponse):
    """Detalle del ticket (W-05 y W-07): datos completos, nombres y comentarios visibles para el usuario."""

    reporter_name: str | None
    assigned_analyst_name: str | None
    comments: list[CommentResponse]

    @classmethod
    def from_detail(cls, detail: TicketDetail) -> "TicketDetailResponse":
        ticket, names = detail.ticket, detail.names
        base = TicketResponse.from_domain(ticket).model_dump()
        comments = [
            CommentResponse(
                id=c.id,
                author_id=c.author_id,
                author_name=names.get(c.author_id),
                content=c.content,
                is_ai_generated=c.is_ai_generated,
                is_internal_note=c.is_internal_note,
                created_at=c.created_at,
            )
            for c in ticket.comments
            if detail.include_internal_notes or not c.is_internal_note
        ]
        return cls(
            **base,
            reporter_name=names.get(ticket.reporter_id),
            assigned_analyst_name=names.get(ticket.assigned_analyst_id) if ticket.assigned_analyst_id else None,
            comments=comments,
        )


class EvidenceContentResponse(BaseModel):
    """Captura lista para mostrarse en un widget Image de Appsmith (src = data_url)."""

    id: uuid.UUID
    file_name: str
    mime_type: str
    size_bytes: int
    data_url: str = Field(..., description="data:<mime>;base64,<contenido>")

    @classmethod
    def from_file(cls, evidence: EvidenceFile) -> "EvidenceContentResponse":
        encoded = base64.b64encode(evidence.content).decode("ascii")
        return cls(
            id=evidence.id,
            file_name=evidence.file_name,
            mime_type=evidence.mime_type,
            size_bytes=len(evidence.content),
            data_url=f"data:{evidence.mime_type};base64,{encoded}",
        )


class TicketStatusHistoryEntryResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    previous_status: str
    new_status: str
    changed_by: uuid.UUID | None
    changed_by_name: str
    reason: str | None
    changed_at: datetime

    @classmethod
    def from_view(cls, item: TicketStatusHistoryEntryView) -> "TicketStatusHistoryEntryResponse":
        return cls(
            id=item.id,
            ticket_id=item.ticket_id,
            previous_status=item.previous_status,
            new_status=item.new_status,
            changed_by=item.changed_by,
            changed_by_name=item.changed_by_name,
            reason=item.reason,
            changed_at=item.changed_at,
        )


class TicketStatusHistoryResponse(BaseModel):
    ticket_id: uuid.UUID
    items: list[TicketStatusHistoryEntryResponse]

    @classmethod
    def from_view(cls, view: TicketStatusHistoryView) -> "TicketStatusHistoryResponse":
        return cls(
            ticket_id=view.ticket_id,
            items=[TicketStatusHistoryEntryResponse.from_view(i) for i in view.items],
        )
