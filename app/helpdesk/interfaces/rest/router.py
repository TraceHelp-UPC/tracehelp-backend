"""Endpoints REST del Bounded Context Helpdesk.

Tickets, colas, estados, escalamiento y calificaciones.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.helpdesk.application.status_change_policy import Actor
from app.helpdesk.application.ticket_command_service import (
    AcceptSelfServiceCommand,
    AssignTicketCommand,
    ChangeTicketStatusCommand,
    CorrectTicketClassificationCommand,
    EscalateTicketCommand,
    PostMessageCommand,
    RegisterTicketCommand,
    RejectSelfServiceCommand,
    ReturnToL1Command,
    TicketCommandService,
    UploadedFile,
)
from app.helpdesk.application.ticket_queries import QueueScope
from app.helpdesk.application.ticket_query_service import TicketQueryService
from app.helpdesk.domain.enums import ImpactLevel, TicketCategory, TicketPriority, TicketStatus
from app.helpdesk.domain.ticket import MAX_EVIDENCES
from app.helpdesk.interfaces.rest.dependencies import get_ticket_command_service, get_ticket_query_service
from app.helpdesk.domain.exceptions import (
    InvalidTicketStateTransitionError,
    TicketNotFoundError,
    TicketStatusChangeForbiddenError,
)
from app.helpdesk.interfaces.rest.schemas import (
    AssignTicketRequest,
    ChangeTicketStatusRequest,
    CorrectTicketClassificationRequest,
    EscalateTicketRequest,
    EvidenceContentResponse,
    MessagePageResponse,
    MessageResponse,
    PostMessageRequest,
    RejectSelfServiceRequest,
    ReturnToL1Request,
    TicketDetailResponse,
    TicketPageResponse,
    TicketResponse,
    TicketStatusHistoryResponse,
)
from app.iam.domain.permissions import Permission
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, get_current_user, require_permission
from app.shared.domain.exceptions import DomainValidationError
from app.shared.domain.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PageRequest

router = APIRouter(tags=["Helpdesk"])


@router.post(
    "/tickets",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un incidente",
    responses={
        400: {"description": "Datos o imagen no válidos"},
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El rol no puede registrar incidentes"},
    },
)
def register_ticket(
    title: Annotated[str, Form(max_length=200, description="Asunto del incidente")],
    description: Annotated[str, Form(description="Descripción del problema")],
    impact_level: Annotated[ImpactLevel, Form(description="Impacto declarado: LOW, MEDIUM o HIGH")],
    affected_module: Annotated[str | None, Form(max_length=100, description="Sistema o módulo afectado")] = None,
    screenshots: Annotated[
        list[UploadFile],
        File(
            description="Capturas PNG o JPG de hasta 10 MB",
            json_schema_extra={"items": {"type": "string", "format": "binary"}},
        ),
    ] = [],
    current_user: CurrentUser = Depends(require_permission(Permission.TICKETS_CREATE)),
    service: TicketCommandService = Depends(get_ticket_command_service),
) -> TicketResponse:
    """Registra un incidente con texto y capturas de pantalla opcionales (US10, TS04).

    Al registrarse, el ticket queda en estado OPEN y se publica el evento TicketRegistered para el triaje.
    """
    files = [f for f in (screenshots or []) if f.filename]
    if len(files) > MAX_EVIDENCES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Se permiten como máximo {MAX_EVIDENCES} capturas por ticket.")

    uploads = [UploadedFile(file_name=f.filename, content=f.file.read()) for f in files]
    command = RegisterTicketCommand(
        workspace_id=current_user.workspace_id,
        reporter_id=current_user.id,
        title=title,
        description=description,
        impact_level=impact_level,
        affected_module=affected_module,
        screenshots=uploads,
    )
    try:
        ticket = service.register(command)
    except DomainValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.detail) from exc
    return TicketResponse.from_domain(ticket)


@router.patch(
    "/tickets/{ticket_id}/status",
    response_model=TicketResponse,
    summary="Cambiar el estado de un ticket",
    responses={
        400: {"description": "Datos no válidos (por ejemplo, motivo demasiado largo)"},
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El usuario no puede hacer este cambio de estado"},
        404: {"description": "El ticket no existe o no es visible para el usuario"},
        422: {"description": "El cambio no está permitido por la máquina de estados"},
    },
)
def change_ticket_status(
    ticket_id: uuid.UUID,
    body: ChangeTicketStatusRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: TicketCommandService = Depends(get_ticket_command_service),
) -> TicketResponse:
    """Mueve el ticket a otro estado según la máquina de estados del Capítulo V (TS04).

    Transiciones permitidas y quién puede hacerlas:
    - OPEN → PENDING_ASSIGNMENT: soporte (tickets:manage). OPEN → SELF_SERVICE_PROPOSED la hace el triaje automático.
    - SELF_SERVICE_PROPOSED → RESOLVED / PENDING_ASSIGNMENT: el colaborador que reportó.
    - PENDING_ASSIGNMENT → ASSIGNED_L1: soporte (el ticket queda asignado a quien lo toma).
    - ASSIGNED_L1 → PENDING_ASSIGNMENT / RESOLVED: soporte. ASSIGNED_L1 → ESCALATED_L2: tickets:escalate.
    - ESCALATED_L2 → ASSIGNED_L1 / RESOLVED: tickets:resolve_escalated.
    - RESOLVED → CLOSED / REOPENED: el colaborador que reportó.
    - REOPENED → ASSIGNED_L1: soporte.
    """
    actor = Actor(id=current_user.id, workspace_id=current_user.workspace_id, permissions=current_user.permissions)
    command = ChangeTicketStatusCommand(
        ticket_id=ticket_id, actor=actor, target_status=body.status, reason=body.reason
    )
    try:
        ticket = service.change_status(command)
    except TicketNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.detail) from exc
    except InvalidTicketStateTransitionError as exc:
        raise HTTPException(422, exc.detail) from exc
    except TicketStatusChangeForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, exc.detail) from exc
    except DomainValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.detail) from exc
    return TicketResponse.from_domain(ticket)


@router.patch(
    "/tickets/{ticket_id}/classification",
    response_model=TicketResponse,
    summary="Establecer o corregir la categoría y prioridad del ticket",
    responses={
        400: {"description": "Categoría fuera del catálogo o datos inválidos"},
        401: {"description": "Token ausente o inválido"},
        403: {"description": "Requiere el permiso tickets:manage"},
        404: {"description": "El ticket no existe"},
    },
)
def correct_ticket_classification(
    ticket_id: uuid.UUID,
    body: CorrectTicketClassificationRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.TICKETS_MANAGE)),
    service: TicketCommandService = Depends(get_ticket_command_service),
) -> TicketResponse:
    """Permite al analista establecer o corregir la categoría técnica y prioridad del ticket (US27, T42)."""
    parsed_category: TicketCategory | None = None
    if body.category is not None:
        try:
            parsed_category = TicketCategory(body.category.strip())
        except ValueError as exc:
            valid = ", ".join(c.value for c in TicketCategory)
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Categoría inválida '{body.category}'. Las categorías permitidas son: {valid}.",
            ) from exc

    command = CorrectTicketClassificationCommand(
        ticket_id=ticket_id,
        actor=Actor(id=current_user.id, workspace_id=current_user.workspace_id, permissions=current_user.permissions),
        category=parsed_category,
        priority=body.priority,
        reason=body.reason,
    )
    try:
        ticket = service.correct_classification(command)
    except TicketNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.detail) from exc
    except TicketStatusChangeForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, exc.detail) from exc
    except DomainValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.detail) from exc
    return TicketResponse.from_domain(ticket)


@router.post(
    "/tickets/{ticket_id}/assign",
    response_model=TicketResponse,
    summary="Asignar un ticket a un analista disponible",
    responses={
        400: {"description": "El analista indicado no existe o no es personal de soporte"},
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El usuario no tiene permiso para asignar tickets"},
        404: {"description": "El ticket no existe"},
        422: {"description": "El analista se encuentra UNAVAILABLE o el ticket no puede asignarse"},
    },
)
def assign_ticket(
    ticket_id: uuid.UUID,
    body: AssignTicketRequest = AssignTicketRequest(),
    current_user: CurrentUser = Depends(get_current_user),
    service: TicketCommandService = Depends(get_ticket_command_service),
) -> TicketResponse:
    """Asigna el ticket a un analista disponible (AVAILABLE) y lo pasa a ASSIGNED_L1 (US24, T47)."""
    command = AssignTicketCommand(
        ticket_id=ticket_id,
        actor=Actor(id=current_user.id, workspace_id=current_user.workspace_id, permissions=current_user.permissions),
        analyst_id=body.analyst_id,
        reason=body.reason,
    )
    try:
        ticket = service.assign_ticket(command)
    except TicketNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.detail) from exc
    except TicketStatusChangeForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, exc.detail) from exc
    except InvalidTicketStateTransitionError as exc:
        raise HTTPException(422, exc.detail) from exc
    except DomainValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.detail) from exc
    return TicketResponse.from_domain(ticket)


# --- Consultas (TS08) ---------------------------------------------------------------------------------------

_PAGE_ERRORS = {
    400: {"description": "Página fuera de rango o tamaño de página no válido"},
    401: {"description": "Token ausente o inválido"},
}
PageNumber = Annotated[int, Query(description="Número de página, desde 1")]
PageSize = Annotated[int, Query(description=f"Tickets por página, de 1 a {MAX_PAGE_SIZE}")]
SearchText = Annotated[str | None, Query(max_length=100, description="Texto del asunto o código (TK-0042)")]


def _actor(user: CurrentUser) -> Actor:
    return Actor(id=user.id, workspace_id=user.workspace_id, permissions=user.permissions)


@router.get(
    "/tickets/queue",
    response_model=TicketPageResponse,
    summary="Bandeja del analista",
    responses={**_PAGE_ERRORS, 403: {"description": "El rol no atiende tickets (requiere tickets:manage)"}},
)
def get_ticket_queue(
    scope: Annotated[QueueScope, Query(description="mine: mi cola · unassigned: pendientes de asignación · escalated: en Nivel 2 · all: todos los activos")] = QueueScope.MINE,
    status_filter: Annotated[TicketStatus | None, Query(alias="status", description="Filtra por estado")] = None,
    priority: Annotated[TicketPriority | None, Query(description="Filtra por prioridad")] = None,
    search: SearchText = None,
    page: PageNumber = 1,
    size: PageSize = DEFAULT_PAGE_SIZE,
    current_user: CurrentUser = Depends(require_permission(Permission.TICKETS_MANAGE)),
    service: TicketQueryService = Depends(get_ticket_query_service),
) -> TicketPageResponse:
    """Tickets del workspace para la Mesa de ayuda (W-06), ordenados por prioridad (CRITICAL primero) y antigüedad."""
    listing = service.queue(
        _actor(current_user),
        scope=scope,
        status=status_filter,
        priority=priority,
        search=search,
        page=PageRequest(page=page, size=size),
    )
    return TicketPageResponse.from_listing(listing)


@router.get(
    "/tickets/my-history",
    response_model=TicketPageResponse,
    summary="Mis tickets",
    responses={**_PAGE_ERRORS, 403: {"description": "El rol no puede consultar sus tickets"}},
)
def get_my_ticket_history(
    status_filter: Annotated[TicketStatus | None, Query(alias="status", description="Filtra por estado")] = None,
    search: SearchText = None,
    page: PageNumber = 1,
    size: PageSize = DEFAULT_PAGE_SIZE,
    current_user: CurrentUser = Depends(require_permission(Permission.TICKETS_READ_OWN)),
    service: TicketQueryService = Depends(get_ticket_query_service),
) -> TicketPageResponse:
    """Incidentes que reportó el usuario (W-04), del más reciente al más antiguo."""
    listing = service.my_history(
        _actor(current_user), status=status_filter, search=search, page=PageRequest(page=page, size=size)
    )
    return TicketPageResponse.from_listing(listing)


@router.get(
    "/tickets/{ticket_id}",
    response_model=TicketDetailResponse,
    summary="Detalle de un ticket",
    responses={
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El ticket es de otro colaborador"},
        404: {"description": "El ticket no existe"},
    },
)
def get_ticket_detail(
    ticket_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: TicketQueryService = Depends(get_ticket_query_service),
) -> TicketDetailResponse:
    """Detalle con evidencias, comentarios y recomendación de autoservicio (W-03, W-05, W-07).

    Lo ven quien reportó el ticket y el equipo de soporte. Las notas internas solo se muestran al equipo
    de soporte. El campo `self_service_recommendation` solo aparece cuando el ticket está en
    `SELF_SERVICE_PROPOSED` con citas válidas; en cualquier otro estado o baja confianza es `null`.
    """
    return TicketDetailResponse.from_detail(service.detail(_actor(current_user), ticket_id))


@router.get(
    "/tickets/{ticket_id}/evidences/{evidence_id}",
    response_model=EvidenceContentResponse,
    summary="Ver una captura del ticket",
    responses={
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El ticket es de otro colaborador"},
        404: {"description": "El ticket o la captura no existen"},
    },
)
def get_ticket_evidence(
    ticket_id: uuid.UUID,
    evidence_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: TicketQueryService = Depends(get_ticket_query_service),
) -> EvidenceContentResponse:
    """Devuelve la captura como data URL para mostrarla en un widget Image de Appsmith."""
    return EvidenceContentResponse.from_file(service.evidence(_actor(current_user), ticket_id, evidence_id))


@router.get(
    "/tickets/{ticket_id}/history",
    response_model=TicketStatusHistoryResponse,
    summary="Historial de cambios de estado del ticket",
    responses={
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El ticket es de otro colaborador"},
        404: {"description": "El ticket no existe"},
    },
)
def get_ticket_status_history(
    ticket_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: TicketQueryService = Depends(get_ticket_query_service),
) -> TicketStatusHistoryResponse:
    """Devuelve la línea de tiempo cronológica de cambios de estado del ticket (US14, T45)."""
    return TicketStatusHistoryResponse.from_view(service.history(_actor(current_user), ticket_id))


# --- Conversación del ticket (US26) ---------------------------------------------------------------------------

MESSAGES_DEFAULT_PAGE_SIZE = 50
_TICKET_ID_EXAMPLE = "6f1c2a3b-8d4e-4f10-9a7b-2c3d4e5f6a7b"


def _problem(
    status_code: int,
    slug: str,
    title: str,
    detail: str,
    description: str | None = None,
    instance_suffix: str = "messages",
) -> dict:
    return {
        "description": description or title,
        "content": {
            "application/problem+json": {
                "example": {
                    "type": f"urn:tracehelp:problems:{slug}",
                    "title": title,
                    "status": status_code,
                    "detail": detail,
                    "instance": f"/api/v1/tickets/{_TICKET_ID_EXAMPLE}/{instance_suffix}",
                }
            }
        },
    }


_MESSAGE_EXAMPLE = {
    "id": "c3d4e5f6-1111-4aaa-8bbb-222233334444",
    "ticket_id": _TICKET_ID_EXAMPLE,
    "author_id": "1a2b3c4d-0000-4000-8000-000000000001",
    "author_name": "Carlos Mendoza",
    "from_reporter": True,
    "content": "Adjunto: el error aparece solo cuando estoy en la VPN.",
    "is_internal_note": False,
    "is_ai_generated": False,
    "created_at": "2026-11-20T13:20:41Z",
}


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar un mensaje en el ticket",
    responses={
        201: {"content": {"application/json": {"example": _MESSAGE_EXAMPLE}}},
        401: {"description": "Token ausente o inválido"},
        403: _problem(403, "internal-note-not-allowed", "Acceso denegado", "Solo el equipo de soporte puede registrar notas internas."),
        404: _problem(404, "ticket-not-found", "Recurso no encontrado", "El ticket no existe."),
        409: _problem(
            409,
            "ticket-closed",
            "Conflicto con el estado actual",
            "El ticket TK-0042 está resuelto y no admite mensajes; reábrelo si necesitas continuar la conversación.",
            description="El ticket está RESOLVED o CLOSED y no admite nuevos mensajes (D30)",
        ),
        422: {
            "description": "Mensaje vacío, de solo espacios o de más de 2000 caracteres",
            "content": {
                "application/problem+json": {
                    "example": {
                        "type": "urn:tracehelp:problems:validation-error",
                        "title": "Datos de entrada no válidos",
                        "status": 422,
                        "detail": "Hay datos no válidos en la solicitud. content: no puede superar los 2000 caracteres.",
                        "instance": f"/api/v1/tickets/{_TICKET_ID_EXAMPLE}/messages",
                        "errors": [{"field": "content", "message": "no puede superar los 2000 caracteres", "type": "string_too_long"}],
                    }
                }
            },
        },
    },
)
def post_ticket_message(
    ticket_id: uuid.UUID,
    body: PostMessageRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: TicketCommandService = Depends(get_ticket_command_service),
) -> MessageResponse:
    """Escribe un mensaje en la conversación del ticket (US26). Lo usan W-05 (colaborador) y W-07 (soporte).

    Pueden escribir quien reportó el ticket y el equipo de soporte (tickets:manage) del mismo workspace, en
    cualquier estado salvo RESOLVED y CLOSED (D30). En RESOLVED el colaborador debe reabrir el ticket para
    volver a escribir; tanto RESOLVED como CLOSED devuelven 409 `urn:tracehelp:problems:ticket-closed`. Solo el
    soporte puede marcar `is_internal_note`: la nota interna nunca la ve el colaborador. El texto se guarda tal
    cual; el evento MessagePosted no lo incluye.
    """
    posted = service.post_message(
        PostMessageCommand(
            ticket_id=ticket_id,
            actor=_actor(current_user),
            content=body.content,
            is_internal_note=body.is_internal_note,
        )
    )
    comment = posted.comment
    return MessageResponse(
        id=comment.id,
        ticket_id=posted.ticket_id,
        author_id=comment.author_id,
        author_name=posted.author_name,
        from_reporter=posted.from_reporter,
        content=comment.content,
        is_internal_note=comment.is_internal_note,
        is_ai_generated=comment.is_ai_generated,
        created_at=comment.created_at,
    )


@router.get(
    "/tickets/{ticket_id}/messages",
    response_model=MessagePageResponse,
    summary="Conversación del ticket",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"items": [_MESSAGE_EXAMPLE], "page": 1, "size": 50, "total": 1, "total_pages": 1}
                }
            }
        },
        400: _problem(400, "invalid-page-request", "Solicitud no válida", "La página 3 no existe: hay 1 página(s) de 50 resultados."),
        401: {"description": "Token ausente o inválido"},
        403: _problem(403, "ticket-access-denied", "Acceso denegado", "No tienes acceso a este ticket: solo lo ven quien lo reportó y el equipo de soporte."),
        404: _problem(404, "ticket-not-found", "Recurso no encontrado", "El ticket no existe."),
    },
)
def get_ticket_messages(
    ticket_id: uuid.UUID,
    page: PageNumber = 1,
    size: Annotated[int, Query(description=f"Mensajes por página, de 1 a {MAX_PAGE_SIZE}")] = MESSAGES_DEFAULT_PAGE_SIZE,
    current_user: CurrentUser = Depends(get_current_user),
    service: TicketQueryService = Depends(get_ticket_query_service),
) -> MessagePageResponse:
    """Mensajes del ticket en orden cronológico (el más antiguo primero), paginados (US26, W-05 y W-07).

    Las notas internas solo las ve el equipo de soporte; para el colaborador se excluyen también del total.
    """
    listing = service.messages(_actor(current_user), ticket_id, PageRequest(page=page, size=size))
    return MessagePageResponse.from_listing(listing)


# --- Autoservicio (US12, T76) ---------------------------------------------------------------------------------

def _self_service_problem(
    status_code: int, slug: str, title: str, detail: str, path_suffix: str, description: str | None = None
) -> dict:
    return {
        "description": description or title,
        "content": {
            "application/problem+json": {
                "example": {
                    "type": f"urn:tracehelp:problems:{slug}",
                    "title": title,
                    "status": status_code,
                    "detail": detail,
                    "instance": f"/api/v1/tickets/{_TICKET_ID_EXAMPLE}/self-service/{path_suffix}",
                }
            }
        },
    }


_SELF_SERVICE_TICKET_ACCEPTED_EXAMPLE = {
    "id": _TICKET_ID_EXAMPLE,
    "code": "TK-0042",
    "title": "VPN error 809 al conectar desde casa",
    "description": "Al intentar conectar la VPN aparece error 809.",
    "affected_module": "VPN",
    "impact_level": "MEDIUM",
    "status": "RESOLVED",
    "priority": "MEDIUM",
    "category": "Red/VPN",
    "current_tier": "SELF_SERVICE",
    "reporter_id": "1a2b3c4d-0000-4000-8000-000000000001",
    "assigned_analyst_id": None,
    "escalated_group": None,
    "escalated_at": None,
    "assigned_specialist_id": None,
    "specialist_claimed_at": None,
    "created_at": "2026-11-20T13:15:00Z",
    "updated_at": "2026-11-20T13:18:10Z",
    "resolved_at": "2026-11-20T13:18:10Z",
    "closed_at": None,
    "evidences": [],
}

_SELF_SERVICE_TICKET_REJECTED_EXAMPLE = {
    **_SELF_SERVICE_TICKET_ACCEPTED_EXAMPLE,
    "status": "PENDING_ASSIGNMENT",
    "current_tier": "TIER_L1",
    "resolved_at": None,
}


@router.post(
    "/tickets/{ticket_id}/self-service/accept",
    response_model=TicketResponse,
    summary="Aceptar la recomendación de autoservicio",
    responses={
        200: {"content": {"application/json": {"example": _SELF_SERVICE_TICKET_ACCEPTED_EXAMPLE}}},
        401: {"description": "Token ausente o inválido"},
        403: _self_service_problem(
            403,
            "ticket-status-change-forbidden",
            "Acceso denegado",
            "Solo el colaborador que reportó el incidente puede responder a la recomendación de autoservicio.",
            "accept",
            description="Quien llama no es el colaborador que reportó el ticket",
        ),
        404: _self_service_problem(
            404,
            "ticket-not-found",
            "Recurso no encontrado",
            "El ticket no existe.",
            "accept",
            description="El ticket no existe o pertenece a otro workspace",
        ),
        422: _self_service_problem(
            422,
            "invalid-ticket-state-transition",
            "Regla de negocio incumplida",
            "El ticket debe estar en SELF_SERVICE_PROPOSED para aceptar el autoservicio (estado actual: PENDING_ASSIGNMENT).",
            "accept",
            description="El ticket no está en estado SELF_SERVICE_PROPOSED",
        ),
    },
)
def accept_self_service(
    ticket_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: TicketCommandService = Depends(get_ticket_command_service),
) -> TicketResponse:
    """Confirma que la recomendación de autoservicio resolvió el incidente (US12, T76).

    Solo el colaborador que reportó el ticket puede ejecutarlo cuando el ticket está en `SELF_SERVICE_PROPOSED`.
    Transiciona el ticket a `RESOLVED` manteniendo `current_tier = SELF_SERVICE` y registra el evento
    `SelfServiceAccepted` en la bitácora de auditoría.
    """
    ticket = service.accept_self_service(AcceptSelfServiceCommand(ticket_id=ticket_id, actor=_actor(current_user)))
    return TicketResponse.from_domain(ticket)


@router.post(
    "/tickets/{ticket_id}/self-service/reject",
    response_model=TicketResponse,
    summary="Rechazar la recomendación de autoservicio y solicitar un analista",
    responses={
        200: {"content": {"application/json": {"example": _SELF_SERVICE_TICKET_REJECTED_EXAMPLE}}},
        401: {"description": "Token ausente o inválido"},
        403: _self_service_problem(
            403,
            "ticket-status-change-forbidden",
            "Acceso denegado",
            "Solo el colaborador que reportó el incidente puede responder a la recomendación de autoservicio.",
            "reject",
            description="Quien llama no es el colaborador que reportó el ticket",
        ),
        404: _self_service_problem(
            404,
            "ticket-not-found",
            "Recurso no encontrado",
            "El ticket no existe.",
            "reject",
            description="El ticket no existe o pertenece a otro workspace",
        ),
        422: _self_service_problem(
            422,
            "invalid-ticket-state-transition",
            "Regla de negocio incumplida",
            "El ticket debe estar en SELF_SERVICE_PROPOSED para rechazar el autoservicio (estado actual: RESOLVED).",
            "reject",
            description="El ticket no está en SELF_SERVICE_PROPOSED o el motivo supera 500 caracteres",
        ),
    },
)
def reject_self_service(
    ticket_id: uuid.UUID,
    body: RejectSelfServiceRequest | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    service: TicketCommandService = Depends(get_ticket_command_service),
) -> TicketResponse:
    """Rechaza la recomendación de autoservicio y deriva el ticket a soporte Nivel 1 (US12, T76).

    Solo el colaborador que reportó el ticket puede ejecutarlo cuando está en `SELF_SERVICE_PROPOSED`.
    Transiciona el ticket a `PENDING_ASSIGNMENT` (`current_tier = TIER_L1`), reabre el diagnóstico a
    `PENDING_REVIEW` para que un analista L1 pueda revisarlo en HITL (D10) y registra `SelfServiceRejected`.
    """
    ticket = service.reject_self_service(
        RejectSelfServiceCommand(
            ticket_id=ticket_id,
            actor=_actor(current_user),
            reason=body.reason if body else None,
        )
    )
    return TicketResponse.from_domain(ticket)


# --- Escalamiento a Nivel 2 y devolución a Nivel 1 (US17) -----------------------------------------------------

_ESCALATED_TICKET_EXAMPLE = {
    "id": _TICKET_ID_EXAMPLE,
    "code": "TK-0042",
    "title": "VPN error 809 al conectar desde casa",
    "description": "Al conectar a la VPN aparece el código 809.",
    "affected_module": "VPN corporativa",
    "impact_level": "MEDIUM",
    "status": "ESCALATED_L2",
    "priority": "HIGH",
    "category": "Red/VPN",
    "current_tier": "TIER_L2",
    "reporter_id": "1a2b3c4d-0000-4000-8000-000000000001",
    "assigned_analyst_id": "1a2b3c4d-0000-4000-8000-000000000002",
    "escalated_group": "REDES",
    "escalated_at": "2026-11-20T15:02:11Z",
    "assigned_specialist_id": None,
    "specialist_claimed_at": None,
    "created_at": "2026-11-20T13:10:00Z",
    "updated_at": "2026-11-20T15:02:11Z",
    "resolved_at": None,
    "closed_at": None,
    "evidences": [],
}

_RETURNED_TICKET_EXAMPLE = {
    **_ESCALATED_TICKET_EXAMPLE,
    "status": "ASSIGNED_L1",
    "current_tier": "TIER_L1",
    "updated_at": "2026-11-20T15:35:00Z",
}


@router.post(
    "/tickets/{ticket_id}/escalate",
    response_model=TicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Escalar un ticket a Soporte Nivel 2",
    responses={
        200: {"content": {"application/json": {"example": _ESCALATED_TICKET_EXAMPLE}}},
        401: {"description": "Token ausente o inválido"},
        403: _problem(
            403,
            "forbidden",
            "Acceso denegado",
            "No tienes permiso para realizar esta acción.",
            description="El rol no posee el permiso tickets:escalate",
            instance_suffix="escalate",
        ),
        404: _problem(
            404,
            "ticket-not-found",
            "Recurso no encontrado",
            "El ticket no existe.",
            instance_suffix="escalate",
        ),
        422: _problem(
            422,
            "invalid-ticket-state-transition",
            "Regla de negocio incumplida",
            "No se puede cambiar el ticket de PENDING_ASSIGNMENT a ESCALATED_L2. Desde PENDING_ASSIGNMENT solo se puede pasar a: ASSIGNED_L1.",
            description="El ticket no está en ASSIGNED_L1, o el grupo especialista/motivo es inválido (validation-error)",
            instance_suffix="escalate",
        ),
    },
)
def escalate_ticket(
    ticket_id: uuid.UUID,
    body: EscalateTicketRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.TICKETS_ESCALATE)),
    service: TicketCommandService = Depends(get_ticket_command_service),
) -> TicketResponse:
    """Deriva un ticket en ASSIGNED_L1 al grupo especialista Nivel 2 indicado (US17, T79).

    Conserva al analista L1 original (`assigned_analyst_id`) para permitir devoluciones posteriores, limpia
    cualquier reclamo L2 previo y registra automáticamente un snapshot de contexto (clasificación, triaje IA,
    OCR anonimizado y fuentes citadas) como nota interna visible solo para soporte. Publica `TicketStatusChanged`
    y `TicketEscalated`.
    """
    ticket = service.escalate(
        EscalateTicketCommand(
            ticket_id=ticket_id,
            actor=_actor(current_user),
            specialist_group=body.specialist_group,
            reason=body.reason,
        )
    )
    return TicketResponse.from_domain(ticket)


@router.post(
    "/tickets/{ticket_id}/return-to-l1",
    response_model=TicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Devolver un ticket escalado a Soporte Nivel 1",
    responses={
        200: {"content": {"application/json": {"example": _RETURNED_TICKET_EXAMPLE}}},
        400: _problem(
            400,
            "invalid-ticket-data",
            "Solicitud no válida",
            "El ticket no tiene un analista L1 original asignado para devolverlo.",
            description="Ticket legado en ESCALATED_L2 sin analista L1 original asignado",
            instance_suffix="return-to-l1",
        ),
        401: {"description": "Token ausente o inválido"},
        403: _problem(
            403,
            "ticket-status-change-forbidden",
            "Acceso denegado",
            "El ticket está escalado al grupo REDES.",
            description="Sin permiso tickets:resolve_escalated o especialista de otro grupo",
            instance_suffix="return-to-l1",
        ),
        404: _problem(
            404,
            "ticket-not-found",
            "Recurso no encontrado",
            "El ticket no existe.",
            instance_suffix="return-to-l1",
        ),
        422: _problem(
            422,
            "invalid-ticket-state-transition",
            "Regla de negocio incumplida",
            "Solo se pueden devolver a Nivel 1 los tickets en estado ESCALATED_L2 (estado actual: ASSIGNED_L1).",
            description="El ticket no está en ESCALATED_L2 o requested_info es inválido (validation-error)",
            instance_suffix="return-to-l1",
        ),
    },
)
def return_ticket_to_l1(
    ticket_id: uuid.UUID,
    body: ReturnToL1Request,
    current_user: CurrentUser = Depends(require_permission(Permission.TICKETS_RESOLVE_ESCALATED)),
    service: TicketCommandService = Depends(get_ticket_command_service),
) -> TicketResponse:
    """Devuelve un ticket en ESCALATED_L2 al analista L1 original solicitando información adicional (US17, T79).

    Aplica la guarda `ensure_can_work_escalated` (permiso `tickets:resolve_escalated` y coincidencia de grupo;
    si el ticket tiene `escalated_group = null` cualquier L2 puede devolverlo). Limpia el reclamo L2, conserva
    `escalated_group` y `escalated_at` (historial y cálculo de FCR), registra la solicitud como nota interna y
    publica `TicketStatusChanged` + `TicketReturnedToL1`.
    """
    ticket = service.return_to_l1(
        ReturnToL1Command(
            ticket_id=ticket_id,
            actor=_actor(current_user),
            requested_info=body.requested_info,
        )
    )
    return TicketResponse.from_domain(ticket)
