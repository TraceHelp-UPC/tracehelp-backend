"""Puertos de lectura ACL del contexto Analytics hacia otros contextos (US21, T96).

Analytics nunca importa servicios ni agregados de Helpdesk, Smart Triage ni IAM;
las consultas transversales de solo lectura se declaran aquí y se adaptan en infrastructure/.
"""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TicketTraceSummary:
    id: uuid.UUID
    code: str
    title: str
    status: str
    priority: str
    category: str | None
    reporter_id: uuid.UUID
    reporter_name: str
    assigned_analyst_id: uuid.UUID | None
    assigned_analyst_name: str | None
    created_at: datetime
    resolved_at: datetime | None


@dataclass(frozen=True)
class DiagnosisTraceSummary:
    id: uuid.UUID
    outcome: str
    confidence_level: str | None
    best_score: float | None
    similarity_threshold: float | None
    self_service_threshold: float | None
    model: str | None
    review_status: str
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None


@dataclass(frozen=True)
class TraceSourceItem:
    reference: str
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    citation: str
    similarity: float


@dataclass(frozen=True)
class UserIdentity:
    id: uuid.UUID
    full_name: str
    role: str


@dataclass(frozen=True)
class TicketTraceSnapshot:
    ticket: TicketTraceSummary
    diagnosis: DiagnosisTraceSummary | None
    sources: list[TraceSourceItem]


class ITicketTraceReader(ABC):
    """Puerto ACL de solo lectura para reconstruir la trazabilidad completa de un ticket."""

    @abstractmethod
    def get_ticket_trace_snapshot(
        self, workspace_id: uuid.UUID, ticket_id: uuid.UUID
    ) -> TicketTraceSnapshot | None:
        """Lee ticket, diagnóstico y fuentes consultadas acotados al workspace, o None si no existe."""

    @abstractmethod
    def get_users_by_ids(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, UserIdentity]:
        """Resuelve nombre completo y rol para un conjunto de identificadores de usuario."""
