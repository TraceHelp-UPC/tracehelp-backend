"""Contratos de repositorio del Bounded Context Analytics."""
import uuid
from abc import ABC, abstractmethod

from app.analytics.domain.audit_trail_entry import AuditTrailEntry


class IAuditTrailRepository(ABC):
    """Contrato de persistencia append-only y consulta paginada de registros de auditoría (US15, US21, TS06)."""

    @abstractmethod
    def append(self, entry: AuditTrailEntry) -> AuditTrailEntry:
        """Inserta una nueva entrada inmutable en la bitácora (append-only)."""

    @abstractmethod
    def find_by_ticket(self, ticket_id: uuid.UUID, workspace_id: uuid.UUID) -> list[AuditTrailEntry]:
        """Recupera las entradas de auditoría asociadas a un ticket del workspace."""

    @abstractmethod
    def list_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        ticket_id: uuid.UUID | None = None,
    ) -> tuple[list[AuditTrailEntry], int]:
        """Recupera entradas paginadas del workspace y el total de registros coincidentes."""
