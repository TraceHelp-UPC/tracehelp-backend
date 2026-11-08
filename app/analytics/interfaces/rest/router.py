"""Endpoints REST del Bounded Context Analytics.

Métricas, auditoría, ROI y reportes.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.analytics.application.audit_log_service import AuditLogService
from app.analytics.domain.repositories import AuditLogFilter
from app.analytics.interfaces.rest.dependencies import get_audit_log_service
from app.analytics.interfaces.rest.schemas import AuditLogPageResponse
from app.iam.domain.permissions import Permission
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, require_permission
from app.shared.domain.pagination import InvalidPageRequestError, PageRequest

router = APIRouter(tags=["Analytics"])


def _page_request(page: int, size: int) -> PageRequest:
    try:
        return PageRequest(page=page, size=size)
    except InvalidPageRequestError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.detail) from exc


@router.get(
    "/audit-log",
    response_model=AuditLogPageResponse,
    summary="Consultar la bitácora de auditoría inmutable",
    responses={
        400: {"description": "Parámetros de paginación o rango de fechas inválidos"},
        403: {"description": "Requiere el permiso audit:read (Líder de TI)"},
    },
)
def get_audit_log(
    event_type: str | None = Query(None, description="Filtrar por tipo de evento (ej. AiResolutionReviewed)"),
    ticket_id: uuid.UUID | None = Query(None, description="Filtrar por el ID de un ticket"),
    from_date: datetime | None = Query(None, description="Fecha inicial (ISO 8601)"),
    to_date: datetime | None = Query(None, description="Fecha final (ISO 8601)"),
    page: int = Query(1, description="Número de página (empieza en 1)"),
    size: int = Query(20, description="Entradas por página (1 a 100)"),
    current_user: CurrentUser = Depends(require_permission(Permission.AUDIT_READ)),
    service: AuditLogService = Depends(get_audit_log_service),
) -> AuditLogPageResponse:
    """Lista las entradas de la bitácora de auditoría del workspace del líder de TI (US15, T36)."""
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha inicial no puede ser posterior a la fecha final.")
    page_req = _page_request(page, size)
    criteria = AuditLogFilter(
        workspace_id=current_user.workspace_id,
        event_type=event_type.strip() if event_type else None,
        ticket_id=ticket_id,
        from_date=from_date,
        to_date=to_date,
    )
    try:
        result = service.query(criteria, page_req)
    except InvalidPageRequestError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.detail) from exc
    return AuditLogPageResponse.from_page(result)
