"""Puertos que la capa de aplicación de Helpdesk necesita de la infraestructura."""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessedImage:
    content: bytes
    mime_type: str
    file_name: str


class IImageProcessor(ABC):
    @abstractmethod
    def process(self, content: bytes, file_name: str) -> ProcessedImage:
        """Verifica que el archivo sea una imagen PNG/JPG real y la reduce para almacenarla."""


@dataclass(frozen=True)
class AnalystAssignmentCandidate:
    id: uuid.UUID
    workspace_id: uuid.UUID
    full_name: str
    is_active: bool
    is_support_staff: bool
    is_available: bool


class IAnalystAvailabilityReader(ABC):
    """Puerto ACL hacia IAM para verificar si un analista existe y está disponible (US24, T47)."""

    @abstractmethod
    def get_candidate(self, analyst_id: uuid.UUID) -> AnalystAssignmentCandidate | None:
        """Devuelve los datos del candidato de asignación o None si no existe."""


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text_body: str


class IEmailSender(ABC):
    """Puerto de envío de correos para notificaciones (US19, T91, D14)."""

    @abstractmethod
    def send(self, message: EmailMessage) -> None:
        """Envía el correo de notificación."""


@dataclass(frozen=True)
class NotificationRecipientProfile:
    id: uuid.UUID
    workspace_id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    notify_inapp: bool
    notify_email: bool


class INotificationRecipients(ABC):
    """Puerto ACL hacia IAM para consultar el perfil y canales habilitados de un destinatario (US19, T91)."""

    @abstractmethod
    def notification_profile(self, user_id: uuid.UUID) -> NotificationRecipientProfile | None:
        """Devuelve el perfil y preferencias de notificación del usuario o None si no existe."""

    def profile(self, user_id: uuid.UUID) -> NotificationRecipientProfile | None:
        return self.notification_profile(user_id)
