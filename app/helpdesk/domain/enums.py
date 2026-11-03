"""Enumeraciones del contexto Helpdesk."""
from enum import StrEnum


class TicketStatus(StrEnum):
    """Estados del ticket según la máquina de estados del Capítulo V (las transiciones se implementan en la T15)."""

    OPEN = "OPEN"
    SELF_SERVICE_PROPOSED = "SELF_SERVICE_PROPOSED"
    PENDING_ASSIGNMENT = "PENDING_ASSIGNMENT"
    ASSIGNED_L1 = "ASSIGNED_L1"
    ESCALATED_L2 = "ESCALATED_L2"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"


class TicketPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ImpactLevel(StrEnum):
    """Nivel de impacto declarado por el colaborador en el formulario W-02."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SupportTier(StrEnum):
    SELF_SERVICE = "SELF_SERVICE"
    TIER_L1 = "TIER_L1"
    TIER_L2 = "TIER_L2"
