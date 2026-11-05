"""Máquina de estados del ticket (Capítulo V, TS04).

Es la única fuente de verdad sobre qué cambios de estado son válidos. Quién puede hacer cada cambio
lo decide la capa de aplicación (ver application/status_change_policy.py).
"""
from types import MappingProxyType

from app.helpdesk.domain.enums import SupportTier, TicketStatus
from app.helpdesk.domain.exceptions import InvalidTicketStateTransitionError

S = TicketStatus

ALLOWED_TRANSITIONS: MappingProxyType[TicketStatus, frozenset[TicketStatus]] = MappingProxyType(
    {
        S.OPEN: frozenset({S.SELF_SERVICE_PROPOSED, S.PENDING_ASSIGNMENT}),
        S.SELF_SERVICE_PROPOSED: frozenset({S.RESOLVED, S.PENDING_ASSIGNMENT}),
        S.PENDING_ASSIGNMENT: frozenset({S.ASSIGNED_L1}),
        S.ASSIGNED_L1: frozenset({S.PENDING_ASSIGNMENT, S.RESOLVED, S.ESCALATED_L2}),
        S.ESCALATED_L2: frozenset({S.ASSIGNED_L1, S.RESOLVED}),
        S.RESOLVED: frozenset({S.CLOSED, S.REOPENED}),
        S.REOPENED: frozenset({S.ASSIGNED_L1}),
        S.CLOSED: frozenset(),  # estado final
    }
)

# Nivel de soporte que atiende el ticket en cada estado. RESOLVED y CLOSED conservan el nivel que lo resolvió.
TIER_BY_STATUS: MappingProxyType[TicketStatus, SupportTier] = MappingProxyType(
    {
        S.OPEN: SupportTier.SELF_SERVICE,
        S.SELF_SERVICE_PROPOSED: SupportTier.SELF_SERVICE,
        S.PENDING_ASSIGNMENT: SupportTier.TIER_L1,
        S.ASSIGNED_L1: SupportTier.TIER_L1,
        S.ESCALATED_L2: SupportTier.TIER_L2,
        S.REOPENED: SupportTier.TIER_L1,
    }
)


def allowed_targets(current: TicketStatus) -> frozenset[TicketStatus]:
    return ALLOWED_TRANSITIONS[current]


def can_transition(current: TicketStatus, target: TicketStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def ensure_transition(current: TicketStatus, target: TicketStatus) -> None:
    """Lanza InvalidTicketStateTransitionError si el cambio no está permitido."""
    if can_transition(current, target):
        return
    allowed = sorted(t.value for t in ALLOWED_TRANSITIONS[current])
    hint = f" Desde {current.value} solo se puede pasar a: {', '.join(allowed)}." if allowed else f" {current.value} es un estado final."
    raise InvalidTicketStateTransitionError(f"No se puede cambiar el ticket de {current.value} a {target.value}.{hint}")
