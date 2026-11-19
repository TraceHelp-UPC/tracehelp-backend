"""Endpoints REST del Bounded Context Analytics.

Métricas, auditoría, ROI y reportes.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
from typing import Any

from fastapi import APIRouter, Depends, Query, Response

from app.analytics.application.audit_log_service import AuditLogService
from app.analytics.domain.repositories import AuditLogFilter
from app.analytics.interfaces.rest.dependencies import audit_log_filter, get_audit_log_service
from app.analytics.interfaces.rest.schemas import AuditLogPageResponse
from app.shared.domain.pagination import MAX_PAGE_SIZE, PageRequest

router = APIRouter(tags=["Analytics"])

CANONICAL_PATH = "/api/v1/audit/logs"

_EXAMPLE_ENTRY = {
    "id": "9e8d7c6b-5a49-4382-9170-6f5e4d3c2b1a",
    "workspace_id": "0f0e0d0c-0000-4000-8000-00000000000a",
    "event_type": "AiResolutionReviewed",
    "actor_id": "1a2b3c4d-0000-4000-8000-000000000002",
    "actor_name": "Karim Ramírez",
    "entity_type": "triage_diagnosis",
    "entity_id": "2c3d4e5f-6a7b-4c8d-9e0f-1a2b3c4d5e6f",
    "ticket_id": "6f1c2a3b-8d4e-4f10-9a7b-2c3d4e5f6a7b",
    "detail": {
        "decision": "APPROVE",
        "previous_status": "PENDING_REVIEW",
        "ai_outcome": "GROUNDED",
        "resolves_ticket": True,
        "note": None,
    },
    "integrity_hash": "3f6a0c5e91b2d4f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5ce91b",
    "occurred_at": "2026-11-20T13:25:07.412Z",
}


def _problem_example(type_slug: str, title: str, status: int, detail: str) -> dict[str, Any]:
    return {
        "application/problem+json": {
            "example": {
                "type": f"urn:tracehelp:problems:{type_slug}",
                "title": title,
                "status": status,
                "detail": detail,
                "instance": CANONICAL_PATH,
            }
        }
    }


_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Página de entradas de la bitácora, las más recientes primero.",
        "content": {
            "application/json": {
                "example": {"items": [_EXAMPLE_ENTRY], "page": 1, "size": 20, "total": 1, "total_pages": 1}
            }
        },
    },
    400: {
        "description": "Paginación fuera de rango (invalid-page-request) o rango de fechas invertido (invalid-date-range).",
        "content": _problem_example(
            "invalid-page-request", "Solicitud no válida", 400, "El tamaño de página debe estar entre 1 y 100."
        ),
    },
    401: {
        "description": "Sin token o token inválido o vencido.",
        "content": _problem_example("unauthorized", "No autenticado", 401, "Token no válido o vencido."),
    },
    403: {
        "description": "El rol no tiene el permiso audit:read (solo Líder de TI).",
        "content": _problem_example(
            "forbidden", "Acceso denegado", 403, "Tu rol no tiene el permiso requerido: audit:read."
        ),
    },
    422: {
        "description": "Parámetro con tipo inválido (UUID, fecha, page o size no numéricos).",
        "content": _problem_example(
            "validation-error", "Datos de entrada no válidos", 422, "Uno o más parámetros no son válidos."
        ),
    },
}

_DESCRIPTION = (
    "Lista las entradas de la bitácora de auditoría del workspace del token, de la más reciente a la más antigua. "
    "Filtros combinables: fechas (`from_date`/`to_date`, inclusivas; sin zona horaria se toman como UTC), `ticket_id`, "
    "`event_type` (coincidencia exacta) y `actor_id` (validador u otro actor). "
    f"`page` empieza en 1 y `size` va de 1 a {MAX_PAGE_SIZE}; fuera de rango responde 400. Requiere `audit:read`."
)


def _query(criteria: AuditLogFilter, page: int, size: int, service: AuditLogService) -> AuditLogPageResponse:
    # InvalidPageRequestError llega al manejador global (type invalid-page-request)
    return AuditLogPageResponse.from_page(service.query(criteria, PageRequest(page=page, size=size)))


@router.get(
    "/audit/logs",
    response_model=AuditLogPageResponse,
    summary="Consultar la bitácora de auditoría",
    description=_DESCRIPTION,
    responses=_RESPONSES,
)
def get_audit_logs(
    page: int = Query(1, description="Número de página (empieza en 1)."),
    size: int = Query(20, description=f"Entradas por página (1 a {MAX_PAGE_SIZE})."),
    criteria: AuditLogFilter = Depends(audit_log_filter),
    service: AuditLogService = Depends(get_audit_log_service),
) -> AuditLogPageResponse:
    return _query(criteria, page, size, service)


@router.get(
    "/audit-log",
    response_model=AuditLogPageResponse,
    deprecated=True,
    summary="(Obsoleto) Usa GET /api/v1/audit/logs",
    description="Alias obsoleto de `GET /api/v1/audit/logs`: responde lo mismo y agrega los encabezados "
    "`Deprecation` y `Link` (`successor-version`).\n\n" + _DESCRIPTION,
    responses=_RESPONSES,
)
def get_audit_log_deprecated(
    response: Response,
    page: int = Query(1, description="Número de página (empieza en 1)."),
    size: int = Query(20, description=f"Entradas por página (1 a {MAX_PAGE_SIZE})."),
    criteria: AuditLogFilter = Depends(audit_log_filter),
    service: AuditLogService = Depends(get_audit_log_service),
) -> AuditLogPageResponse:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f'<{CANONICAL_PATH}>; rel="successor-version"'
    return _query(criteria, page, size, service)
