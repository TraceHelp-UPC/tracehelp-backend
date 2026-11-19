"""Implementación SQLAlchemy del repositorio de notificaciones in-app (US19, T91)."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.helpdesk.domain.notification import Notification, NotificationType
from app.helpdesk.domain.repositories import INotificationRepository
from app.helpdesk.infrastructure.persistence.models import NotificationModel


class SqlAlchemyNotificationRepository(INotificationRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, notification: Notification) -> Notification:
        model = self._session.get(NotificationModel, notification.id)
        if model is None:
            model = NotificationModel(id=notification.id)
            self._session.add(model)
        model.workspace_id = notification.workspace_id
        model.recipient_id = notification.recipient_id
        model.ticket_id = notification.ticket_id
        model.type = notification.type.value if isinstance(notification.type, NotificationType) else str(notification.type)
        model.title = notification.title
        model.body = notification.body
        model.data = dict(notification.data)
        model.read_at = notification.read_at
        model.created_at = notification.created_at
        self._session.flush()
        return notification

    def find_by_id_for_recipient(
        self,
        *,
        notification_id: uuid.UUID,
        recipient_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> Notification | None:
        stmt = select(NotificationModel).where(
            NotificationModel.id == notification_id,
            NotificationModel.recipient_id == recipient_id,
            NotificationModel.workspace_id == workspace_id,
        )
        model = self._session.scalars(stmt).one_or_none()
        return self._to_domain(model) if model is not None else None

    def list_for_recipient(
        self,
        *,
        recipient_id: uuid.UUID,
        workspace_id: uuid.UUID,
        unread_only: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[Notification], int]:
        conditions = [
            NotificationModel.recipient_id == recipient_id,
            NotificationModel.workspace_id == workspace_id,
        ]
        if unread_only:
            conditions.append(NotificationModel.read_at.is_(None))
        total = self._session.scalar(select(func.count()).select_from(NotificationModel).where(*conditions)) or 0
        stmt = (
            select(NotificationModel)
            .where(*conditions)
            .order_by(NotificationModel.created_at.desc(), NotificationModel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        items = [self._to_domain(m) for m in self._session.scalars(stmt).all()]
        return items, int(total)

    def count_unread(self, *, recipient_id: uuid.UUID, workspace_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(NotificationModel)
            .where(
                NotificationModel.recipient_id == recipient_id,
                NotificationModel.workspace_id == workspace_id,
                NotificationModel.read_at.is_(None),
            )
        )
        return int(self._session.scalar(stmt) or 0)

    @staticmethod
    def _to_domain(model: NotificationModel) -> Notification:
        return Notification(
            id=model.id,
            workspace_id=model.workspace_id,
            recipient_id=model.recipient_id,
            ticket_id=model.ticket_id,
            type=NotificationType(model.type),
            title=model.title,
            body=model.body,
            data=dict(model.data or {}),
            read_at=model.read_at,
            created_at=model.created_at,
        )
