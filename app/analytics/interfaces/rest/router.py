"""Endpoints REST del Bounded Context Analytics.

Métricas, auditoría, ROI y reportes.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.analytics.application.audit_trail_service import AuditTrailService
from app.analytics.domain.exceptions import InvalidAuditLogDataError
from app.analytics.interfaces.rest.dependencies import get_audit_trail_service
from app.analytics.interfaces.rest.schemas import AuditLogEntryResponse, PaginatedAuditLogResponse
from app.iam.domain.permissions import Permission
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, require_permission

router = APIRouter(tags=["Analytics"])


@router.get(
    "/audit/logs",
    response_model=PaginatedAuditLogResponse,
    status_code=status.HTTP_200_OK,
    summary="Consultar la bitácora inmutable de auditoría",
    responses={
        400: {"description": "Parámetros de paginación fuera de rango"},
        401: {"description": "Token ausente o inválido"},
        403: {"description": "El rol no posee el permiso audit:read"},
    },
)
def list_audit_logs(
    page: int = Query(1, description="Número de página (>= 1)"),
    page_size: int = Query(20, description="Tamaño de página (1..100)"),
    ticket_id: uuid.UUID | None = Query(None, description="Filtrar por ticket específico"),
    current_user: CurrentUser = Depends(require_permission(Permission.AUDIT_READ)),
    service: AuditTrailService = Depends(get_audit_trail_service),
) -> PaginatedAuditLogResponse:
    """Devuelve las entradas de auditoría del workspace verificando el hash SHA-256 de cada fila (US15, US21, TS06)."""
    try:
        entries, total = service.list_workspace_logs(
            workspace_id=current_user.workspace_id,
            page=page,
            page_size=page_size,
            ticket_id=ticket_id,
        )
    except InvalidAuditLogDataError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.detail) from exc
    return PaginatedAuditLogResponse(
        items=[AuditLogEntryResponse.from_domain(e) for e in entries],
        total=total,
        page=page,
        page_size=page_size,
    )
