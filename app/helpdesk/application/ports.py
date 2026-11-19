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


@dataclass(frozen=True)
class TriageContextSource:
    reference: str
    document_title: str
    citation: str
    similarity: float | None = None


@dataclass(frozen=True)
class TriageContextSnapshot:
    outcome: str
    confidence_level: str | None
    best_score: float | None
    summary: str | None
    steps: tuple[str, ...]
    suggested_category: str | None
    suggested_priority: str | None
    ocr_legible: bool | None
    ocr_error_codes: tuple[str, ...]
    ocr_masked_text: str | None
    sources: tuple[TriageContextSource, ...]


class ITriageContextReader(ABC):
    """Puerto ACL de solo lectura hacia triage_diagnoses para el snapshot de escalamiento (US17)."""

    @abstractmethod
    def for_ticket(self, ticket_id: uuid.UUID) -> TriageContextSnapshot | None:
        """Devuelve el contexto de triaje del ticket o None si todavía no existe diagnóstico."""


@dataclass(frozen=True)
class SelfServiceSource:
    reference: str
    document_title: str
    citation: str


@dataclass(frozen=True)
class SelfServiceRecommendation:
    summary: str
    steps: tuple[str, ...]
    match_percentage: int | None
    confidence_label: str
    sources: tuple[SelfServiceSource, ...]


class ISelfServiceRecommendationReader(ABC):
    """Puerto ACL de solo lectura hacia Smart Triage para exponer la propuesta de autoservicio (US12, T76)."""

    @abstractmethod
    def for_ticket(self, ticket_id: uuid.UUID) -> SelfServiceRecommendation | None:
        """Lee la recomendación de autoservicio desde triage_diagnoses solo si está en SELF_SERVICE_PROPOSED."""
