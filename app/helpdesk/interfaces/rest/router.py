"""Endpoints REST del Bounded Context Helpdesk.

Tickets, colas, estados, escalamiento y calificaciones.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.helpdesk.application.status_change_policy import Actor
from app.helpdesk.application.ticket_command_service import (
    ChangeTicketStatusCommand,
    RegisterTicketCommand,
    TicketCommandService,
    UploadedFile,
)
from app.helpdesk.domain.enums import ImpactLevel
from app.helpdesk.domain.ticket import MAX_EVIDENCES
from app.helpdesk.interfaces.rest.dependencies import get_ticket_command_service
from app.helpdesk.domain.exceptions import (
    InvalidTicketStateTransitionError,
    TicketNotFoundError,
    TicketStatusChangeForbiddenError,
)
from app.helpdesk.interfaces.rest.schemas import (
    AnalystAvailabilityRequest,
    AnalystAvailabilityResponse,
    ChangeTicketStatusRequest,
    TicketResponse,
)
from app.iam.domain.enums import AvailabilityStatus
from app.iam.domain.permissions import Permission
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, get_current_user, require_permission
from app.shared.domain.exceptions import DomainValidationError

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


@router.post(
    "/tickets/{ticket_id}/assign",
    response_model=TicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Tomar o asignar un incidente al analista actual",
    responses={
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El rol no tiene permiso para gestionar tickets"},
        404: {"description": "El incidente no existe"},
        422: {"description": "Transición no permitida por la máquina de estados"},
    },
)
def assign_ticket(
    ticket_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.TICKETS_MANAGE)),
    service: TicketCommandService = Depends(get_ticket_command_service),
) -> TicketResponse:
    """Asigna el ticket al analista autenticado y actualiza su estado a ASSIGNED_L1 (US24, T47)."""
    actor = Actor(id=current_user.id, workspace_id=current_user.workspace_id, permissions=current_user.permissions)
    try:
        ticket = service.assign_ticket(ticket_id=ticket_id, actor=actor)
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
    "/analysts/me/availability",
    response_model=AnalystAvailabilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Actualizar estado de disponibilidad del analista",
    responses={
        400: {"description": "Estado de disponibilidad inválido"},
        401: {"description": "Token ausente o inválido"},
        403: {"description": "No tiene permisos de analista"},
    },
)
def update_analyst_availability(
    payload: AnalystAvailabilityRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.TICKETS_MANAGE)),
    session: Session = Depends(get_db),
) -> AnalystAvailabilityResponse:
    """Modifica la disponibilidad operativa del analista (AVAILABLE o UNAVAILABLE) (US24, T47)."""
    try:
        status_enum = AvailabilityStatus(payload.availability)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"El estado '{payload.availability}' no es válido. Use AVAILABLE o UNAVAILABLE.",
        ) from exc

    user_repo = SqlAlchemyUserRepository(session)
    user = user_repo.find_by_id(current_user.id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analista no encontrado.")

    user.set_availability(status_enum)
    user_repo.save(user)
    session.commit()

    return AnalystAvailabilityResponse(
        user_id=user.id,
        availability_status=user.availability_status.value,
    )
