"""Endpoints REST de notificaciones in-app (US19, T91)."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.helpdesk.application.notifications.notification_service import NotificationService
from app.helpdesk.interfaces.rest.dependencies import get_notification_service
from app.helpdesk.interfaces.rest.schemas import NotificationPageResponse, NotificationResponse
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, get_current_user
from app.shared.domain.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PageRequest

router = APIRouter()

_NOTIFICATION_ID_EXAMPLE = "5b6c7d8e-1111-4aaa-8bbb-999900001111"
_TICKET_ID_EXAMPLE = "6f1c2a3b-8d4e-4f10-9a7b-2c3d4e5f6a7b"

_NOTIFICATION_EXAMPLE = {
    "id": _NOTIFICATION_ID_EXAMPLE,
    "type": "TICKET_STATUS_CHANGED",
    "ticket_id": _TICKET_ID_EXAMPLE,
    "ticket_code": "TK-0042",
    "title": "TK-0042: tu ticket está Resuelto",
    "body": "Tu ticket TK-0042 cambió de «En atención» a «Resuelto». Revisa la solución y confírmala.",
    "data": {"ticket_code": "TK-0042", "previous_status": "ASSIGNED_L1", "new_status": "RESOLVED"},
    "read": False,
    "read_at": None,
    "created_at": "2026-11-20T13:30:12Z",
}


def _problem(status_code: int, slug: str, title: str, detail: str, instance: str) -> dict:
    return {
        "description": title,
        "content": {
            "application/problem+json": {
                "example": {
                    "type": f"urn:tracehelp:problems:{slug}",
                    "title": title,
                    "status": status_code,
                    "detail": detail,
                    "instance": instance,
                }
            }
        },
    }


@router.get(
    "/notifications",
    response_model=NotificationPageResponse,
    summary="Listar mis notificaciones",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "items": [_NOTIFICATION_EXAMPLE],
                        "page": 1,
                        "size": 20,
                        "total": 3,
                        "total_pages": 1,
                        "unread_count": 2,
                    }
                }
            }
        },
        400: _problem(
            400,
            "invalid-page-request",
            "Solicitud no válida",
            "La página 3 no existe: hay 1 página(s) de 20 resultados.",
            "/api/v1/notifications",
        ),
        401: _problem(401, "unauthorized", "No autenticado", "Inicia sesión para continuar.", "/api/v1/notifications"),
    },
)
def list_my_notifications(
    unread_only: Annotated[bool, Query(description="Si es true, devuelve solo las notificaciones no leídas")] = False,
    page: Annotated[int, Query(description="Número de página, desde 1")] = 1,
    size: Annotated[int, Query(description=f"Notificaciones por página, de 1 a {MAX_PAGE_SIZE}")] = DEFAULT_PAGE_SIZE,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationPageResponse:
    """Lista las notificaciones in-app del usuario autenticado, ordenadas de la más reciente a la más antigua (US19).

    Incluye siempre `unread_count` con el total global de notificaciones no leídas del usuario sin importar los filtros ni la página.
    """
    listing = service.list_mine(
        recipient_id=current_user.id,
        workspace_id=current_user.workspace_id,
        unread_only=unread_only,
        page=PageRequest(page=page, size=size),
    )
    return NotificationPageResponse.from_listing(listing)


@router.patch(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Marcar una notificación como leída",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {**_NOTIFICATION_EXAMPLE, "read": True, "read_at": "2026-11-20T13:35:00Z"}
                }
            }
        },
        401: _problem(
            401,
            "unauthorized",
            "No autenticado",
            "Inicia sesión para continuar.",
            f"/api/v1/notifications/{_NOTIFICATION_ID_EXAMPLE}/read",
        ),
        404: _problem(
            404,
            "notification-not-found",
            "Recurso no encontrado",
            "La notificación no existe.",
            f"/api/v1/notifications/{_NOTIFICATION_ID_EXAMPLE}/read",
        ),
        422: _problem(
            422,
            "validation-error",
            "Datos de entrada no válidos",
            "Hay datos no válidos en la solicitud. notification_id: no es un identificador válido.",
            "/api/v1/notifications/no-es-uuid/read",
        ),
    },
)
def mark_notification_as_read(
    notification_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    """Marca una notificación propia como leída (US19). Es idempotente: si ya estaba leída, conserva su `read_at` original."""
    notification = service.mark_as_read(
        notification_id=notification_id,
        recipient_id=current_user.id,
        workspace_id=current_user.workspace_id,
    )
    return NotificationResponse.from_domain(notification)
