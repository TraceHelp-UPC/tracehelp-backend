"""Contrato de persistencia del agregado Ticket."""
import uuid
from abc import ABC, abstractmethod

from app.helpdesk.domain.notification import Notification
from app.helpdesk.domain.ticket import Ticket


class ITicketRepository(ABC):
    @abstractmethod
    def save(self, ticket: Ticket) -> Ticket:
        """Inserta o actualiza el ticket con sus evidencias y comentarios. Asigna el número público si es nuevo."""

    @abstractmethod
    def find_by_id(self, ticket_id: uuid.UUID) -> Ticket | None:
        """Devuelve el ticket o None si no existe."""


class INotificationRepository(ABC):
    """Contrato de persistencia de notificaciones in-app del usuario (US19, T91)."""

    @abstractmethod
    def save(self, notification: Notification) -> Notification:
        """Inserta o actualiza una notificación."""

    @abstractmethod
    def find_by_id_for_recipient(
        self,
        *,
        notification_id: uuid.UUID,
        recipient_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> Notification | None:
        """Devuelve la notificación si existe y pertenece al destinatario en el workspace; si no, None."""

    @abstractmethod
    def list_for_recipient(
        self,
        *,
        recipient_id: uuid.UUID,
        workspace_id: uuid.UUID,
        unread_only: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[Notification], int]:
        """Devuelve una página de notificaciones ordenadas por created_at DESC, id DESC y el total."""

    @abstractmethod
    def count_unread(self, *, recipient_id: uuid.UUID, workspace_id: uuid.UUID) -> int:
        """Total de notificaciones no leídas del usuario en el workspace."""
