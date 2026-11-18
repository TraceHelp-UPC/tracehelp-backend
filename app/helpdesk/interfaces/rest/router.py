"""Endpoints REST del Bounded Context Helpdesk.

Tickets, colas, estados, escalamiento y calificaciones.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.helpdesk.application.status_change_policy import Actor
from app.helpdesk.application.ticket_command_service import (
    AssignTicketCommand,
    ChangeTicketStatusCommand,
    CorrectTicketClassificationCommand,
    RegisterTicketCommand,
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
    EvidenceContentResponse,
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
    """Detalle con evidencias y comentarios (W-05, W-07). Lo ven quien lo reportó y el equipo de soporte.

    Las notas internas solo se muestran al equipo de soporte.
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
