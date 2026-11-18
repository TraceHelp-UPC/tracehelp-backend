"""Puertos que la capa de aplicación de Smart Triage necesita de la infraestructura."""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.shared.domain.pii import SanitizedText
from app.smart_triage.domain.diagnosis import DiagnosisDraft
from app.smart_triage.domain.grounding import EvidenceFragment
from app.smart_triage.domain.value_objects import OcrExtractionResult

if TYPE_CHECKING:  # evita una importación circular
    from app.smart_triage.application.grounded_prompt import GroundedPrompt


class LlmProviderError(Exception):
    """El proveedor de IA no respondió o rechazó la solicitud (cuota, red o error del servicio)."""


class LlmProviderNotConfiguredError(LlmProviderError):
    """Falta la clave del proveedor de IA (GEMINI_API_KEY)."""


class InvalidLlmResponseError(Exception):
    """La IA respondió, pero sin el formato JSON esperado o con la respuesta bloqueada."""


class IOcrExtractor(ABC):
    @abstractmethod
    def extract(self, content: bytes) -> OcrExtractionResult:
        """Extrae el texto y los códigos de error de una captura PNG o JPG.

        Nunca envía la imagen fuera del servidor. Lanza InvalidScreenshotError si el archivo no es una imagen.
        """


class IKnowledgeRetriever(ABC):
    """Acceso a los manuales del contexto Knowledge Management (anticorruption layer)."""

    @abstractmethod
    def retrieve(self, workspace_id: uuid.UUID, query: SanitizedText, *, top_k: int) -> list[EvidenceFragment]:
        """Fragmentos más parecidos a la consulta anonimizada, con su cita y similitud coseno."""


class IDiagnosisGenerator(ABC):
    """Modelo de lenguaje que redacta el diagnóstico a partir del prompt fundamentado."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Nombre del modelo, para dejarlo registrado junto al diagnóstico."""

    @abstractmethod
    def generate(self, prompt: "GroundedPrompt") -> DiagnosisDraft:
        """Envía el prompt y devuelve la respuesta sin validar.

        Lanza LlmProviderError si el proveedor falla e InvalidLlmResponseError si la respuesta no tiene el formato pedido.
        """


@dataclass(frozen=True)
class IncidentToTriage:
    """Datos del ticket que necesita el triaje, leídos desde Helpdesk."""

    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    description: str
    affected_module: str | None = None
    screenshots: tuple[bytes, ...] = field(default=(), repr=False)


class ITicketReader(ABC):
    """Acceso de solo lectura a los tickets de Helpdesk (anticorruption layer)."""

    @abstractmethod
    def get(self, ticket_id: uuid.UUID) -> IncidentToTriage | None:
        """Ticket con el contenido de sus capturas, o None si no existe."""

    @abstractmethod
    def find_untriaged_open_ticket_ids(self) -> list[uuid.UUID]:
        """Tickets en OPEN que todavía no tienen diagnóstico (por ejemplo, si la API se reinició a mitad del triaje)."""


@dataclass(frozen=True)
class Reviewer:
    """Analista o especialista que revisa la respuesta de la IA, con los permisos de su token."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    permissions: frozenset[str]


class ITicketResolver(ABC):
    """Resolución del ticket en Helpdesk cuando la revisión entrega una respuesta final (anticorruption layer)."""

    @abstractmethod
    def stage_resolution(
        self, ticket_id: uuid.UUID, reviewer: Reviewer, *, response_text: str, ai_generated: bool
    ) -> list:
        """Deja el ticket en RESOLVED con la respuesta, sin commit. Devuelve los eventos de Helpdesk por publicar.

        Lanza los errores de Helpdesk si el ticket no puede resolverse (404, 403 o 422).
        """


@dataclass(frozen=True)
class TicketAccess:
    """Datos mínimos del ticket para decidir quién puede ver su diagnóstico."""

    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    reporter_id: uuid.UUID
    code: str
    status: str


class ITicketAccessReader(ABC):
    @abstractmethod
    def find_access(self, ticket_id: uuid.UUID) -> TicketAccess | None:
        """Workspace, solicitante y estado del ticket, o None si no existe."""


class IUserNames(ABC):
    @abstractmethod
    def display_names(self, user_ids) -> dict[uuid.UUID, str]:
        """Nombre completo por id de usuario."""
