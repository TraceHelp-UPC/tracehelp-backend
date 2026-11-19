"""Pruebas unitarias de Ticket.post_message y del manejo del evento MessagePosted en la auditoría (US26, T85)."""
import uuid

import pytest

from app.analytics.application.audit_log_service import AuditEventHandler
from app.helpdesk.domain.enums import ImpactLevel, TicketStatus
from app.helpdesk.domain.events import MessagePosted
from app.helpdesk.domain.exceptions import InvalidTicketDataError, TicketClosedError
from app.helpdesk.domain.ticket import MAX_MESSAGE_LENGTH, Ticket

SECRET_TEXT = "Mi usuario es jperez y mi clave es Secreta123"


def _ticket(status: TicketStatus = TicketStatus.ASSIGNED_L1) -> Ticket:
    ticket = Ticket.register(
        workspace_id=uuid.uuid4(),
        reporter_id=uuid.uuid4(),
        title="VPN caída",
        description="No conecta",
        impact_level=ImpactLevel.MEDIUM,
    )
    ticket.pull_events()
    ticket.number = 42
    ticket.status = status
    ticket.assigned_analyst_id = uuid.uuid4()
    return ticket


def test_post_message_adds_trimmed_comment_and_emits_event():
    ticket = _ticket()
    comment = ticket.post_message(author_id=ticket.reporter_id, content="  Hola  ", author_is_reporter=True)

    assert comment in ticket.comments
    assert comment.content == "Hola"
    assert comment.is_internal_note is False and comment.is_ai_generated is False
    events = ticket.pull_events()
    assert len(events) == 1 and isinstance(events[0], MessagePosted)
    event = events[0]
    assert event.message_id == comment.id
    assert event.ticket_code == "TK-0042"
    assert event.author_id == ticket.reporter_id and event.reporter_id == ticket.reporter_id
    assert event.assigned_analyst_id == ticket.assigned_analyst_id
    assert event.author_is_reporter is True and event.is_internal_note is False
    assert event.ticket_status == "ASSIGNED_L1" and event.content_length == 4


def test_event_never_carries_the_text():
    ticket = _ticket()
    ticket.post_message(author_id=uuid.uuid4(), content=SECRET_TEXT, is_internal_note=True)
    event = ticket.pull_events()[0]
    assert not hasattr(event, "content")
    assert SECRET_TEXT not in repr(event.__dict__)
    assert event.is_internal_note is True and event.author_is_reporter is False


@pytest.mark.parametrize(
    ("status", "expected_fragment"),
    [
        (TicketStatus.CLOSED, "está cerrado"),
        (TicketStatus.RESOLVED, "está resuelto"),
    ],
)
def test_post_message_in_resolved_or_closed_ticket_is_rejected_without_side_effects(status, expected_fragment):
    ticket = _ticket(status)
    with pytest.raises(TicketClosedError) as exc_info:
        ticket.post_message(author_id=uuid.uuid4(), content="Hola")
    assert expected_fragment in exc_info.value.detail
    assert ticket.comments == [] and ticket.pull_events() == []


@pytest.mark.parametrize(
    "status", [s for s in TicketStatus if s not in (TicketStatus.RESOLVED, TicketStatus.CLOSED)]
)
def test_post_message_is_allowed_in_every_active_status(status):
    ticket = _ticket(status)
    ticket.post_message(author_id=uuid.uuid4(), content="Hola")
    assert ticket.status is status


@pytest.mark.parametrize("content", ["", "   ", "\n\t "])
def test_post_message_rejects_empty_text(content):
    with pytest.raises(InvalidTicketDataError):
        _ticket().post_message(author_id=uuid.uuid4(), content=content)


def test_post_message_length_limit_counts_after_trimming():
    ticket = _ticket()
    ticket.post_message(author_id=uuid.uuid4(), content="  " + "a" * MAX_MESSAGE_LENGTH + "  ")
    with pytest.raises(InvalidTicketDataError):
        ticket.post_message(author_id=uuid.uuid4(), content="a" * (MAX_MESSAGE_LENGTH + 1))
    assert len(ticket.comments) == 1


def test_add_comment_keeps_no_length_limit_for_hitl_responses():
    ticket = _ticket()
    comment = ticket.add_comment(author_id=uuid.uuid4(), content="r" * 5000, is_ai_generated=True)
    assert len(comment.content) == 5000
    assert ticket.pull_events() == []


def test_audit_entry_for_message_posted_has_explicit_branch_without_text():
    ticket = _ticket()
    comment = ticket.post_message(author_id=ticket.reporter_id, content=SECRET_TEXT, author_is_reporter=True)
    event = ticket.pull_events()[0]

    entry = AuditEventHandler().to_audit_entry(event)

    assert entry is not None
    assert entry.event_type == "MessagePosted"
    assert entry.actor_id == ticket.reporter_id
    assert entry.entity_type == "ticket_message" and entry.entity_id == comment.id
    assert entry.ticket_id == ticket.id
    assert entry.detail == {
        "is_internal_note": False,
        "author_is_reporter": True,
        "ticket_status": "ASSIGNED_L1",
        "content_length": len(SECRET_TEXT),
    }
    assert "jperez" not in repr(entry.detail) and "Secreta123" not in repr(entry.detail)
    assert entry.verify_integrity()
