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
