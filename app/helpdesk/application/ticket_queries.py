"""Contratos del lado de lectura de Helpdesk (TS08): filtros, resúmenes y puertos de consulta.

Las consultas no cargan el agregado completo: leen solo las columnas que necesitan las bandejas
(W-04 Mis tickets, W-06 Mesa de ayuda), sin el contenido binario de las capturas.
"""
import uuid
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.helpdesk.domain.enums import TicketPriority, TicketStatus
from app.shared.domain.pagination import Page, PageRequest

S = TicketStatus

# Estados en los que el ticket todavía necesita trabajo de soporte
ACTIVE_STATUSES = frozenset(
    {S.OPEN, S.SELF_SERVICE_PROPOSED, S.PENDING_ASSIGNMENT, S.ASSIGNED_L1, S.ESCALATED_L2, S.REOPENED}
)


class QueueScope(StrEnum):
    """Pestañas de la bandeja del analista (W-06)."""

    MINE = "mine"  # Mi cola: asignados a mí y aún en atención
    UNASSIGNED = "unassigned"  # Pendientes de asignación
    ESCALATED = "escalated"  # Escalados a Nivel 2
    ALL = "all"  # Todos los activos del workspace


SCOPE_STATUSES: dict[QueueScope, frozenset[TicketStatus]] = {
    QueueScope.MINE: frozenset({S.ASSIGNED_L1, S.ESCALATED_L2, S.REOPENED}),
    QueueScope.UNASSIGNED: frozenset({S.PENDING_ASSIGNMENT}),
    QueueScope.ESCALATED: frozenset({S.ESCALATED_L2}),
    QueueScope.ALL: ACTIVE_STATUSES,
}


class TicketOrder(StrEnum):
    PRIORITY = "priority"  # prioridad (CRITICAL primero) y luego el más antiguo: orden de atención
    RECENT = "recent"  # el más reciente primero: historial del colaborador


@dataclass(frozen=True)
class TicketSearchCriteria:
    workspace_id: uuid.UUID
    statuses: frozenset[TicketStatus] | None = None
    priorities: frozenset[TicketPriority] | None = None
    reporter_id: uuid.UUID | None = None
    assigned_analyst_id: uuid.UUID | None = None
    search: str | None = None
    order: TicketOrder = TicketOrder.RECENT


@dataclass(frozen=True)
class TicketSummary:
    id: uuid.UUID
    number: int
    title: str
    status: TicketStatus
    priority: TicketPriority
    impact_level: str
    current_tier: str
    affected_module: str | None
    reporter_id: uuid.UUID
    assigned_analyst_id: uuid.UUID | None
    evidence_count: int
    created_at: datetime
    updated_at: datetime

    @property
    def code(self) -> str:
        return f"TK-{self.number:04d}"


@dataclass(frozen=True)
class EvidenceFile:
    id: uuid.UUID
    file_name: str
    mime_type: str
    content: bytes


class ITicketReadModel(ABC):
    @abstractmethod
    def search(self, criteria: TicketSearchCriteria, page: PageRequest) -> Page[TicketSummary]:
        """Devuelve la página pedida y el total de tickets que cumplen los filtros."""

    @abstractmethod
    def get_evidence(self, ticket_id: uuid.UUID, evidence_id: uuid.UUID) -> EvidenceFile | None:
        """Contenido de una captura del ticket, o None si no existe."""


class IUserDirectory(ABC):
    """Nombres visibles de los usuarios (los provee IAM)."""

    @abstractmethod
    def display_names(self, user_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Nombre completo por id; los ids desconocidos no aparecen en el resultado."""
