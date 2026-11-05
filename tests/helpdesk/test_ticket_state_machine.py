"""Pruebas unitarias de la máquina de estados del ticket (T15, TS04)."""
import uuid
from itertools import product

import pytest

from app.helpdesk.domain import state_machine
from app.helpdesk.domain.enums import ImpactLevel, SupportTier, TicketStatus
from app.helpdesk.domain.events import TicketStatusChanged
from app.helpdesk.domain.exceptions import InvalidTicketDataError, InvalidTicketStateTransitionError
from app.helpdesk.domain.ticket import Ticket

S = TicketStatus
VALID = [(src, dst) for src, targets in state_machine.ALLOWED_TRANSITIONS.items() for dst in targets]
INVALID = [(src, dst) for src, dst in product(S, S) if (src, dst) not in VALID]
ANALYST = uuid.uuid4()


def _ticket(status: TicketStatus = S.OPEN, assigned: uuid.UUID | None = None) -> Ticket:
    ticket = Ticket.register(
        workspace_id=uuid.uuid4(),
        reporter_id=uuid.uuid4(),
        title="No puedo ingresar al ERP",
        description="Error 0x80070005",
        impact_level=ImpactLevel.MEDIUM,
    )
    ticket.pull_events()
    ticket.status = status
    ticket.current_tier = state_machine.TIER_BY_STATUS.get(status, SupportTier.TIER_L1)
    ticket.assigned_analyst_id = assigned
    return ticket


def test_every_status_has_an_entry_in_the_table():
    assert set(state_machine.ALLOWED_TRANSITIONS) == set(S)


def test_closed_is_a_final_state():
    assert state_machine.allowed_targets(S.CLOSED) == frozenset()


def test_the_table_has_the_thirteen_transitions_of_chapter_v():
    assert len(VALID) == 13


@pytest.mark.parametrize(("source", "target"), VALID, ids=[f"{a}->{b}" for a, b in VALID])
def test_valid_transitions_change_the_status(source, target):
    ticket = _ticket(source, assigned=ANALYST)
    ticket.change_status(target, changed_by=ANALYST)
    assert ticket.status is target


@pytest.mark.parametrize(("source", "target"), INVALID, ids=[f"{a}->{b}" for a, b in INVALID])
def test_invalid_transitions_are_rejected(source, target):
    ticket = _ticket(source, assigned=ANALYST)
    with pytest.raises(InvalidTicketStateTransitionError):
        ticket.change_status(target)
    assert ticket.status is source
    assert ticket.pull_events() == []


def test_error_message_lists_the_allowed_targets():
    with pytest.raises(InvalidTicketStateTransitionError) as exc:
        _ticket(S.OPEN).change_status(S.CLOSED)
    assert "PENDING_ASSIGNMENT" in exc.value.detail and "SELF_SERVICE_PROPOSED" in exc.value.detail


def test_change_emits_ticket_status_changed():
    ticket = _ticket(S.OPEN)
    ticket.change_status(S.PENDING_ASSIGNMENT, changed_by=ANALYST, reason="  Triaje manual  ")
    [event] = ticket.pull_events()
    assert isinstance(event, TicketStatusChanged)
    assert (event.previous_status, event.new_status) == ("OPEN", "PENDING_ASSIGNMENT")
    assert event.changed_by == ANALYST and event.reason == "Triaje manual"


def test_system_changes_have_no_author():
    ticket = _ticket(S.OPEN)
    ticket.change_status(S.SELF_SERVICE_PROPOSED)
    assert ticket.pull_events()[0].changed_by is None


def test_assigning_sets_the_analyst_and_tier():
    ticket = _ticket(S.PENDING_ASSIGNMENT)
    ticket.change_status(S.ASSIGNED_L1, assignee_id=ANALYST)
    assert ticket.assigned_analyst_id == ANALYST
    assert ticket.current_tier is SupportTier.TIER_L1


def test_assigning_without_analyst_is_rejected():
    with pytest.raises(InvalidTicketDataError):
        _ticket(S.PENDING_ASSIGNMENT).change_status(S.ASSIGNED_L1)


def test_releasing_a_ticket_clears_the_analyst():
    ticket = _ticket(S.ASSIGNED_L1, assigned=ANALYST)
    ticket.change_status(S.PENDING_ASSIGNMENT)
    assert ticket.assigned_analyst_id is None


def test_escalation_moves_to_tier_two_and_return_keeps_the_analyst():
    ticket = _ticket(S.ASSIGNED_L1, assigned=ANALYST)
    ticket.change_status(S.ESCALATED_L2)
    assert ticket.current_tier is SupportTier.TIER_L2
    ticket.change_status(S.ASSIGNED_L1)
    assert ticket.current_tier is SupportTier.TIER_L1 and ticket.assigned_analyst_id == ANALYST


def test_resolve_close_and_reopen_update_timestamps():
    ticket = _ticket(S.ASSIGNED_L1, assigned=ANALYST)
    ticket.change_status(S.RESOLVED)
    assert ticket.resolved_at is not None and ticket.current_tier is SupportTier.TIER_L1
    ticket.change_status(S.REOPENED)
    assert ticket.resolved_at is None
    ticket.change_status(S.ASSIGNED_L1)
    ticket.change_status(S.RESOLVED)
    ticket.change_status(S.CLOSED)
    assert ticket.closed_at is not None


def test_reason_longer_than_500_characters_is_rejected():
    with pytest.raises(InvalidTicketDataError):
        _ticket(S.OPEN).change_status(S.PENDING_ASSIGNMENT, reason="x" * 501)
