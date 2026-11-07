"""Puertos que la capa de aplicación de Smart Triage necesita de la infraestructura."""
import uuid
from abc import ABC, abstractmethod

from app.shared.domain.pii import SanitizedText
from app.smart_triage.domain.grounding import EvidenceFragment
from app.smart_triage.domain.value_objects import OcrExtractionResult


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
