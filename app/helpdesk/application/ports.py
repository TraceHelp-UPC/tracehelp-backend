"""Puertos que la capa de aplicación de Helpdesk necesita de la infraestructura."""
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
