"""Puertos que la capa de aplicación de Smart Triage necesita de la infraestructura."""
import uuid
from abc import ABC, abstractmethod
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
