"""Quién puede hacer cada cambio de estado del ticket (TS04).

La máquina de estados (domain/state_machine.py) dice qué cambios existen; esta política dice quién los hace.
Un cambio que no aparece en la tabla solo lo puede hacer el sistema (por ejemplo, OPEN -> SELF_SERVICE_PROPOSED
lo decide el triaje automático de Smart Triage).
"""
import uuid
from dataclasses import dataclass

from app.helpdesk.domain.enums import TicketStatus
from app.helpdesk.domain.exceptions import TicketStatusChangeForbiddenError
from app.helpdesk.domain.ticket import Ticket
from app.iam.domain.permissions import Permission

S = TicketStatus
REPORTER = "reporter"  # solo el colaborador que reportó el incidente


@dataclass(frozen=True)
class Actor:
    """Usuario que pide el cambio, con los permisos de su token."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    permissions: frozenset[str]

    def can(self, permission: Permission) -> bool:
        return permission.value in self.permissions

    @property
    def is_support_staff(self) -> bool:
        return self.can(Permission.TICKETS_MANAGE)


RULES: dict[tuple[TicketStatus, TicketStatus], Permission | str] = {
    # Triaje manual cuando la IA no pudo clasificar el ticket
    (S.OPEN, S.PENDING_ASSIGNMENT): Permission.TICKETS_MANAGE,
    # El colaborador acepta o rechaza la solución de autoservicio (US24)
    (S.SELF_SERVICE_PROPOSED, S.RESOLVED): REPORTER,
    (S.SELF_SERVICE_PROPOSED, S.PENDING_ASSIGNMENT): REPORTER,
    # Atención en Nivel 1
    (S.PENDING_ASSIGNMENT, S.ASSIGNED_L1): Permission.TICKETS_MANAGE,
    (S.ASSIGNED_L1, S.PENDING_ASSIGNMENT): Permission.TICKETS_MANAGE,
    (S.ASSIGNED_L1, S.RESOLVED): Permission.TICKETS_MANAGE,
    (S.ASSIGNED_L1, S.ESCALATED_L2): Permission.TICKETS_ESCALATE,
    # Atención en Nivel 2
    (S.ESCALATED_L2, S.ASSIGNED_L1): Permission.TICKETS_RESOLVE_ESCALATED,
    (S.ESCALATED_L2, S.RESOLVED): Permission.TICKETS_RESOLVE_ESCALATED,
    # El colaborador confirma la solución o reabre el ticket
    (S.RESOLVED, S.CLOSED): REPORTER,
    (S.RESOLVED, S.REOPENED): REPORTER,
    (S.REOPENED, S.ASSIGNED_L1): Permission.TICKETS_MANAGE,
}


def authorize(actor: Actor, ticket: Ticket, target: TicketStatus) -> None:
    """Lanza TicketStatusChangeForbiddenError si el actor no puede hacer este cambio."""
    rule = RULES.get((ticket.status, target))
    if rule is None:
        raise TicketStatusChangeForbiddenError(
            f"El cambio de {ticket.status.value} a {target.value} lo realiza el sistema automáticamente."
        )
    if rule == REPORTER:
        if actor.id != ticket.reporter_id:
            raise TicketStatusChangeForbiddenError("Solo el colaborador que reportó el incidente puede hacer este cambio.")
        return
    if not actor.can(rule):
        raise TicketStatusChangeForbiddenError(f"Tu rol no tiene el permiso requerido: {rule.value}.")
