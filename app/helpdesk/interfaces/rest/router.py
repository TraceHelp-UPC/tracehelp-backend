"""Endpoints REST del Bounded Context Helpdesk.

Tickets, colas, estados, escalamiento y calificaciones.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.helpdesk.application.ticket_command_service import (
    RegisterTicketCommand,
    TicketCommandService,
    UploadedFile,
)
from app.helpdesk.domain.enums import ImpactLevel
from app.helpdesk.domain.ticket import MAX_EVIDENCES
from app.helpdesk.interfaces.rest.dependencies import get_ticket_command_service
from app.helpdesk.interfaces.rest.schemas import TicketResponse
from app.iam.domain.permissions import Permission
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, require_permission
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
    screenshots: Annotated[list[UploadFile] | None, File(description="Capturas PNG o JPG de hasta 10 MB")] = None,
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
