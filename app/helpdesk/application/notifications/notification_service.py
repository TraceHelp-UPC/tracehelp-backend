"""Casos de uso de consulta y lectura de notificaciones in-app (US19, T91)."""
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.helpdesk.domain.exceptions import NotificationNotFoundError
from app.helpdesk.domain.notification import Notification
from app.helpdesk.domain.repositories import INotificationRepository
from app.shared.domain.pagination import Page, PageRequest


@dataclass(frozen=True)
class NotificationListing:
    """Página de notificaciones del usuario más el total global de no leídas."""

    page: Page[Notification]
    unread_count: int


class NotificationService:
    """Consulta paginada de notificaciones propias y marcado idempotente como leídas."""

    def __init__(self, *, session: Session | None, notifications: INotificationRepository) -> None:
        self._session = session
        self._notifications = notifications

    def list_mine(
        self,
        *,
        recipient_id: uuid.UUID,
        workspace_id: uuid.UUID,
        unread_only: bool = False,
        page: PageRequest | None = None,
    ) -> NotificationListing:
        req = page or PageRequest()
        items, total = self._notifications.list_for_recipient(
            recipient_id=recipient_id,
            workspace_id=workspace_id,
            unread_only=unread_only,
            offset=req.offset,
            limit=req.size,
        )
        req.ensure_in_range(total)
        unread_count = self._notifications.count_unread(recipient_id=recipient_id, workspace_id=workspace_id)
        return NotificationListing(
            page=Page(items=items, page=req.page, size=req.size, total=total),
            unread_count=unread_count,
        )

    def mark_as_read(
        self,
        *,
        notification_id: uuid.UUID,
        recipient_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> Notification:
        notification = self._notifications.find_by_id_for_recipient(
            notification_id=notification_id,
            recipient_id=recipient_id,
            workspace_id=workspace_id,
        )
        if notification is None:
            raise NotificationNotFoundError("La notificación no existe.")
        if not notification.is_read:
            notification.mark_as_read()
            self._notifications.save(notification)
            if self._session is not None:
                self._session.commit()
        return notification
