"""Pruebas unitarias de asignación de incidentes y disponibilidad (US24, T47)."""
import uuid

from app.helpdesk.domain.enums import ImpactLevel, SupportTier, TicketPriority, TicketStatus
from app.helpdesk.domain.ticket import Ticket
from app.iam.domain.enums import AvailabilityStatus, RoleName
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress, PasswordHash


def _make_ticket(initial_status: TicketStatus = TicketStatus.PENDING_ASSIGNMENT) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        reporter_id=uuid.uuid4(),
        title="Problema de red interna",
        description="Fallo de conectividad al switch 3",
        affected_module="REDES",
        impact_level=ImpactLevel.HIGH,
        status=initial_status,
        priority=TicketPriority.HIGH,
        current_tier=SupportTier.TIER_L1,
    )


def test_assign_to_moves_pending_ticket_to_assigned_l1():
    ticket = _make_ticket(TicketStatus.PENDING_ASSIGNMENT)
    analyst_id = uuid.uuid4()

    ticket.assign_to(analyst_id)

    assert ticket.assigned_analyst_id == analyst_id
    assert ticket.status is TicketStatus.ASSIGNED_L1
    events = ticket.pull_events()
    assert len(events) == 1
    assert events[0].new_status == TicketStatus.ASSIGNED_L1.value


def test_analyst_set_availability_updates_status():
    user = User(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        full_name="Karim Ramírez",
        email=EmailAddress("karim@empresa.pe"),
        password_hash=PasswordHash("$2b$04$fakehashfakehashfakehashfakehashfakehash1234"),
        role=RoleName.ANALYST_L1,
        department="TI",
        availability_status=AvailabilityStatus.AVAILABLE,
    )

    user.set_availability(AvailabilityStatus.UNAVAILABLE)

    assert user.availability_status is AvailabilityStatus.UNAVAILABLE
