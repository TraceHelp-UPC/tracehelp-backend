"""Puertos que la capa de aplicación de Smart Triage necesita de la infraestructura."""
from abc import ABC, abstractmethod

from app.smart_triage.domain.value_objects import OcrExtractionResult


class IOcrExtractor(ABC):
    @abstractmethod
    def extract(self, content: bytes) -> OcrExtractionResult:
        """Extrae el texto y los códigos de error de una captura PNG o JPG.

        Nunca envía la imagen fuera del servidor. Lanza InvalidScreenshotError si el archivo no es una imagen.
        """
