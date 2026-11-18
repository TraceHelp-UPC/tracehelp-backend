"""Contrato de persistencia de la bitácora de auditoría (US15, T36)."""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.analytics.domain.audit_entry import AuditEntry


@dataclass(frozen=True)
class AuditLogFilter:
    workspace_id: uuid.UUID
    event_type: str | None = None
    ticket_id: uuid.UUID | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None


class IAuditLogRepository(ABC):
    @abstractmethod
    def append(self, entry: AuditEntry) -> AuditEntry:
        """Inserta una nueva entrada en la bitácora (append-only)."""

    @abstractmethod
    def query(self, criteria: AuditLogFilter, *, offset: int = 0, limit: int = 20) -> tuple[list[AuditEntry], int]:
        """Devuelve las entradas que cumplen los filtros (más recientes primero) y el total."""
