"""DTOs de respuesta del contexto Helpdesk."""
import base64
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.helpdesk.application.ports import SelfServiceRecommendation
from app.helpdesk.application.ticket_queries import EvidenceFile, MessageView, TicketSummary
from app.helpdesk.application.ticket_query_service import (
    MessageListing,
    TicketDetail,
    TicketListing,
    TicketStatusHistoryEntryView,
    TicketStatusHistoryView,
)
from app.helpdesk.domain.enums import TicketCategory, TicketPriority, TicketStatus
from app.helpdesk.domain.ticket import MAX_MESSAGE_LENGTH, MAX_REASON_LENGTH, Ticket


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


class SelfServiceSourceResponse(BaseModel):
    """Fuente citada en una recomendación de autoservicio, sin datos internos (US12)."""

    reference: str = Field(..., examples=["F1"])
    document_title: str = Field(..., examples=["Manual de Conectividad VPN"])
    citation: str = Field(..., examples=["guia-vpn.md, sección «Error 809», párr. 1"])


class SelfServiceRecommendationResponse(BaseModel):
    """Recomendación de autoservicio expuesta al colaborador cuando el ticket está en SELF_SERVICE_PROPOSED (US12)."""

    summary: str = Field(
        ..., examples=["El error 809 ocurre cuando el router doméstico bloquea el protocolo L2TP/IPsec."]
    )
    steps: list[str] = Field(
        ...,
        examples=[
            [
                "Abre Configuración de red y selecciona el perfil VPN corporativo.",
                "Cambia el tipo de protocolo a IKEv2 y guarda los cambios.",
            ]
        ],
    )
    match_percentage: int | None = Field(
        None, ge=0, le=100, description="Porcentaje redondeado de coincidencia (0–100)", examples=[89]
    )
    confidence_label: str = Field(..., examples=["Alta coincidencia"])
    sources: list[SelfServiceSourceResponse]

    @classmethod
    def from_recommendation(cls, rec: SelfServiceRecommendation) -> "SelfServiceRecommendationResponse":
        return cls(
            summary=rec.summary,
            steps=list(rec.steps),
            match_percentage=rec.match_percentage,
            confidence_label=rec.confidence_label,
            sources=[
                SelfServiceSourceResponse(
                    reference=s.reference,
                    document_title=s.document_title,
                    citation=s.citation,
                )
                for s in rec.sources
            ],
        )


class RejectSelfServiceRequest(BaseModel):
    """Motivo opcional del colaborador al rechazar una recomendación de autoservicio (US12)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"reason": "Seguí los pasos pero el error 809 continúa apareciendo."}],
        },
    )

    reason: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=MAX_REASON_LENGTH),
    ] = Field(
        None,
        description=f"Motivo opcional del rechazo (máximo {MAX_REASON_LENGTH} caracteres)",
    )


class TicketDetailResponse(TicketResponse):
    """Detalle del ticket (W-05 y W-07): datos completos, nombres y comentarios visibles para el usuario."""

    reporter_name: str | None
    assigned_analyst_name: str | None
    comments: list[CommentResponse]
    self_service_recommendation: SelfServiceRecommendationResponse | None = Field(
        None,
        description=(
            "Recomendación de autoservicio disponible solo cuando el ticket está en SELF_SERVICE_PROPOSED "
            "con citas válidas; null en cualquier otro estado o ante baja confianza."
        ),
    )

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
        recommendation = (
            SelfServiceRecommendationResponse.from_recommendation(detail.self_service_recommendation)
            if detail.self_service_recommendation is not None
            else None
        )
        return cls(
            **base,
            reporter_name=names.get(ticket.reporter_id),
            assigned_analyst_name=names.get(ticket.assigned_analyst_id) if ticket.assigned_analyst_id else None,
            comments=comments,
            self_service_recommendation=recommendation,
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


class PostMessageRequest(BaseModel):
    """Mensaje nuevo en la conversación del ticket (US26)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"content": "Adjunto: el error aparece solo cuando estoy en la VPN.", "is_internal_note": False},
                {"content": "Revisar el perfil del usuario antes de escalar.", "is_internal_note": True},
            ]
        },
    )

    content: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_LENGTH),
    ] = Field(..., description=f"Texto del mensaje, de 1 a {MAX_MESSAGE_LENGTH} caracteres (sin contar los espacios de los extremos)")
    is_internal_note: bool = Field(
        False, description="true marca una nota interna visible solo para soporte; el colaborador recibe 403"
    )


class MessageResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    author_name: str | None
    from_reporter: bool = Field(..., description="true si lo escribió quien reportó el ticket (para alinear burbujas)")
    content: str
    is_internal_note: bool
    is_ai_generated: bool
    created_at: datetime

    @classmethod
    def from_view(cls, m: MessageView, *, reporter_id: uuid.UUID, names: dict[uuid.UUID, str]) -> "MessageResponse":
        return cls(
            id=m.id,
            ticket_id=m.ticket_id,
            author_id=m.author_id,
            author_name=names.get(m.author_id),
            from_reporter=m.author_id == reporter_id,
            content=m.content,
            is_internal_note=m.is_internal_note,
            is_ai_generated=m.is_ai_generated,
            created_at=m.created_at,
        )


class MessagePageResponse(BaseModel):
    items: list[MessageResponse]
    page: int = Field(..., examples=[1])
    size: int = Field(..., examples=[50])
    total: int = Field(..., description="Mensajes visibles para el usuario (sin notas internas si no es soporte)", examples=[2])
    total_pages: int = Field(..., examples=[1])

    @classmethod
    def from_listing(cls, listing: MessageListing) -> "MessagePageResponse":
        page = listing.page
        return cls(
            items=[MessageResponse.from_view(m, reporter_id=listing.reporter_id, names=listing.names) for m in page.items],
            page=page.page,
            size=page.size,
            total=page.total,
            total_pages=page.total_pages,
        )
