"""Contratos de persistencia del contexto Smart Triage."""
import uuid
from abc import ABC, abstractmethod

from app.smart_triage.domain.triage_diagnosis import TriageDiagnosis


class ITriageDiagnosisRepository(ABC):
    @abstractmethod
    def save(self, diagnosis: TriageDiagnosis) -> TriageDiagnosis:
        """Inserta o actualiza el diagnóstico. No hace commit."""

    @abstractmethod
    def find_by_ticket_id(self, ticket_id: uuid.UUID) -> TriageDiagnosis | None:
        """Diagnóstico del ticket, o None si todavía no fue triado."""
