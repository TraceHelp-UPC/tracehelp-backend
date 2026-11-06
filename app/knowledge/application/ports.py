"""Puertos que la capa de aplicación de Knowledge Management necesita de la infraestructura."""
from abc import ABC, abstractmethod


class IDocumentStorage(ABC):
    """Almacenamiento del archivo original del manual."""

    @abstractmethod
    def save(self, *, file_name: str, mime_type: str, content: bytes) -> str:
        """Guarda el archivo y devuelve su ubicación (storage_uri)."""

    @abstractmethod
    def load(self, storage_uri: str) -> bytes:
        """Devuelve el contenido del archivo guardado."""
