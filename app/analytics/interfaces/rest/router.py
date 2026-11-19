"""Endpoints REST del Bounded Context Analytics.

Métricas, auditoría, trazabilidad, verificación de integridad, ROI y reportes.
Las rutas se montan bajo /api/v1 en app/main.py.
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Response

from app.analytics.application.audit_log_service import AuditLogService
from app.analytics.domain.repositories import AuditLogFilter
from app.analytics.interfaces.rest.dependencies import audit_log_filter, get_audit_log_service
from app.analytics.interfaces.rest.schemas import (
    AuditIntegrityVerificationResponse,
    AuditLogPageResponse,
    TicketAuditTraceResponse,
)
from app.iam.domain.permissions import Permission
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, require_permission
from app.shared.domain.pagination import MAX_PAGE_SIZE, PageRequest

router = APIRouter(tags=["Analytics"])

CANONICAL_PATH = "/api/v1/audit/logs"

_EXAMPLE_ENTRY = {
    "id": "9e8d7c6b-5a49-4382-9170-6f5e4d3c2b1a",
    "seq": 104,
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
    "previous_hash": "8a4f12c90b7e99a0123456789abcdef0123456789abcdef0123456789abcdef0",
    "occurred_at": "2026-11-20T13:25:07.412Z",
}

_EXAMPLE_VERIFY = {
    "entry_id": "9e8d7c6b-5a49-4382-9170-6f5e4d3c2b1a",
    "seq": 104,
    "valid": True,
    "status": "VALID",
    "hash_valid": True,
    "chain_valid": True,
    "stored_hash": "3f6a0c5e91b2d4f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5ce91b",
    "computed_hash": "3f6a0c5e91b2d4f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5ce91b",
    "previous_entry_id": "7d6c5b4a-3210-4987-8654-3210fedcba98",
    "stored_previous_hash": "8a4f12c90b7e99a0123456789abcdef0123456789abcdef0123456789abcdef0",
    "expected_previous_hash": "8a4f12c90b7e99a0123456789abcdef0123456789abcdef0123456789abcdef0",
    "verified_at": "2026-11-20T15:40:00Z",
    "message": "Registro íntegro: el hash SHA-256 y el encadenamiento con el registro anterior coinciden.",
}

_EXAMPLE_TRACE = {
    "ticket": {
        "id": "6f1c2a3b-8d4e-4f10-9a7b-2c3d4e5f6a7b",
        "code": "TK-0042",
        "title": "VPN corporativa devuelve error 809",
        "status": "RESOLVED",
        "priority": "HIGH",
        "category": "Red/VPN",
        "reporter_id": "1a2b3c4d-0000-4000-8000-000000000001",
        "reporter_name": "Carlos Mendoza",
        "assigned_analyst_id": "1a2b3c4d-0000-4000-8000-000000000002",
        "assigned_analyst_name": "Karim Ramírez",
        "created_at": "2026-11-20T13:10:00Z",
        "resolved_at": "2026-11-20T13:25:07Z",
    },
    "diagnosis": {
        "id": "2c3d4e5f-6a7b-4c8d-9e0f-1a2b3c4d5e6f",
        "outcome": "ANSWERED",
        "confidence_level": "GROUNDED",
        "best_score": 0.7842,
        "similarity_threshold": 0.68,
        "self_service_threshold": 0.80,
        "model": "gemini-2.5-flash-lite",
        "review_status": "APPROVED",
    },
    "sources": [
        {
            "reference": "F1",
            "chunk_id": "a1b2c3d4-0000-4000-8000-000000000011",
            "document_id": "d1e2f3a4-0000-4000-8000-000000000099",
            "document_title": "Manual VPN Corporativa v2",
            "citation": "manual-vpn.pdf, pág. 4, párr. 2",
            "similarity": 0.7842,
        }
    ],
    "authorizing_analyst": {
        "id": "1a2b3c4d-0000-4000-8000-000000000002",
        "name": "Karim Ramírez",
        "role": "ANALYST_L1",
        "decision": "APPROVE",
        "reviewed_at": "2026-11-20T13:25:07.412Z",
    },
    "events": [_EXAMPLE_ENTRY],
    "total_events": 1,
    "all_hashes_valid": True,
}


def _problem_example(
    type_slug: str, title: str, status: int, detail: str, *, instance: str = CANONICAL_PATH
) -> dict[str, Any]:
    return {
        "application/problem+json": {
            "example": {
                "type": f"urn:tracehelp:problems:{type_slug}",
                "title": title,
                "status": status,
                "detail": detail,
                "instance": instance,
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

_VERIFY_INSTANCE = "/api/v1/audit/logs/9e8d7c6b-5a49-4382-9170-6f5e4d3c2b1a/verify"
_VERIFY_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Resultado de la verificación de integridad (`VALID`, `TAMPERED` o `CHAIN_BROKEN`).",
        "content": {"application/json": {"example": _EXAMPLE_VERIFY}},
    },
    401: {
        "description": "Sin token o token inválido o vencido.",
        "content": _problem_example(
            "unauthorized", "No autenticado", 401, "Token no válido o vencido.", instance=_VERIFY_INSTANCE
        ),
    },
    403: {
        "description": "El rol no tiene el permiso audit:read (solo Líder de TI).",
        "content": _problem_example(
            "forbidden",
            "Acceso denegado",
            403,
            "Tu rol no tiene el permiso requerido: audit:read.",
            instance=_VERIFY_INSTANCE,
        ),
    },
    404: {
        "description": "La entrada de auditoría no existe o pertenece a otro workspace.",
        "content": _problem_example(
            "audit-entry-not-found",
            "Recurso no encontrado",
            404,
            "La entrada de auditoría solicitada no existe.",
            instance=_VERIFY_INSTANCE,
        ),
    },
    422: {
        "description": "Identificador `entry_id` con formato UUID inválido.",
        "content": _problem_example(
            "validation-error",
            "Datos de entrada no válidos",
            422,
            "Hay datos no válidos en la solicitud. entry_id: no es un identificador válido.",
            instance="/api/v1/audit/logs/no-uuid/verify",
        ),
    },
}

_TRACE_INSTANCE = "/api/v1/audit/tickets/6f1c2a3b-8d4e-4f10-9a7b-2c3d4e5f6a7b/trace"
_TRACE_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Trazabilidad completa del ticket: resumen, diagnóstico, fuentes consultadas, analista autorizador y eventos cronológicos.",
        "content": {"application/json": {"example": _EXAMPLE_TRACE}},
    },
    401: {
        "description": "Sin token o token inválido o vencido.",
        "content": _problem_example(
            "unauthorized", "No autenticado", 401, "Token no válido o vencido.", instance=_TRACE_INSTANCE
        ),
    },
    403: {
        "description": "El rol no tiene el permiso audit:read (solo Líder de TI).",
        "content": _problem_example(
            "forbidden",
            "Acceso denegado",
            403,
            "Tu rol no tiene el permiso requerido: audit:read.",
            instance=_TRACE_INSTANCE,
        ),
    },
    404: {
        "description": "El ticket no existe o pertenece a otro workspace.",
        "content": _problem_example(
            "ticket-not-found",
            "Recurso no encontrado",
            404,
            "El ticket solicitado no existe.",
            instance=_TRACE_INSTANCE,
        ),
    },
    422: {
        "description": "Identificador `ticket_id` con formato UUID inválido.",
        "content": _problem_example(
            "validation-error",
            "Datos de entrada no válidos",
            422,
            "Hay datos no válidos en la solicitud. ticket_id: no es un identificador válido.",
            instance="/api/v1/audit/tickets/no-uuid/trace",
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


@router.get(
    "/audit/logs/{entry_id}/verify",
    response_model=AuditIntegrityVerificationResponse,
    summary="Verificar integridad criptográfica de una entrada de auditoría",
    description=(
        "Recalcula el sello SHA-256 de la entrada de bitácora y comprueba su encadenamiento (`previous_hash`) "
        "con el registro predecesor del mismo workspace. Siempre devuelve 200 OK cuando la entrada existe, "
        "reportando `status` (`VALID`, `TAMPERED` o `CHAIN_BROKEN`). Requiere `audit:read`."
    ),
    responses=_VERIFY_RESPONSES,
)
def verify_audit_entry(
    entry_id: uuid.UUID = Path(..., description="Identificador UUID de la entrada de auditoría."),
    current_user: CurrentUser = Depends(require_permission(Permission.AUDIT_READ)),
    service: AuditLogService = Depends(get_audit_log_service),
) -> AuditIntegrityVerificationResponse:
    report = service.verify_entry(current_user.workspace_id, entry_id)
    return AuditIntegrityVerificationResponse.from_report(report)


@router.get(
    "/audit/tickets/{ticket_id}/trace",
    response_model=TicketAuditTraceResponse,
    summary="Consultar trazabilidad completa de un ticket",
    description=(
        "Devuelve el expediente de auditoría completo de un ticket del workspace: metadatos del ticket, "
        "diagnóstico RAG, fuentes técnicas consultadas, analista autorizador de la revisión HITL y la "
        "línea de tiempo cronológica ascendente de eventos de auditoría (`occurred_at ASC, seq ASC`) "
        "junto con la validación de hashes `all_hashes_valid`. Requiere `audit:read`."
    ),
    responses=_TRACE_RESPONSES,
)
def get_ticket_audit_trace(
    ticket_id: uuid.UUID = Path(..., description="Identificador UUID del ticket a auditar."),
    current_user: CurrentUser = Depends(require_permission(Permission.AUDIT_READ)),
    service: AuditLogService = Depends(get_audit_log_service),
) -> TicketAuditTraceResponse:
    view = service.ticket_trace(current_user.workspace_id, ticket_id)
    return TicketAuditTraceResponse.from_view(view)
