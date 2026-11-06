"""Contrato de repositorio del agregado TriageDiagnosis."""
import uuid
from abc import ABC, abstractmethod

from app.smart_triage.domain.triage_diagnosis import TriageDiagnosis


class ITriageDiagnosisRepository(ABC):
    """Contrato de persistencia y consulta para TriageDiagnosis."""

    @abstractmethod
    def save(self, diagnosis: TriageDiagnosis) -> TriageDiagnosis:
        """Guarda o actualiza un diagnóstico."""

    @abstractmethod
    def find_by_id(self, diagnosis_id: uuid.UUID) -> TriageDiagnosis | None:
        """Busca un diagnóstico por su ID."""

    @abstractmethod
    def find_by_ticket_id(self, ticket_id: uuid.UUID) -> TriageDiagnosis | None:
        """Busca el diagnóstico asociado a un ticket."""
