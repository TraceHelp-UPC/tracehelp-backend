"""Pruebas unitarias del agregado Ticket y del value object VisualEvidence (US10)."""
import uuid

import pytest

from app.helpdesk.domain.enums import ImpactLevel, SupportTier, TicketPriority, TicketStatus
from app.helpdesk.domain.events import TicketRegistered
from app.helpdesk.domain.exceptions import InvalidTicketDataError, InvalidVisualEvidenceError
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.domain.value_objects import MAX_EVIDENCE_BYTES, VisualEvidence

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


def _register(**overrides) -> Ticket:
    data = dict(
        workspace_id=uuid.uuid4(),
        reporter_id=uuid.uuid4(),
        title="No puedo ingresar al ERP",
        description="Al iniciar sesión aparece el error 0x80070005.",
        impact_level=ImpactLevel.HIGH,
        affected_module="ERP",
    )
    data.update(overrides)
    return Ticket.register(**data)


def test_register_creates_open_ticket_with_priority_from_impact():
    ticket = _register()
    assert ticket.status is TicketStatus.OPEN
    assert ticket.priority is TicketPriority.HIGH
    assert ticket.current_tier is SupportTier.SELF_SERVICE
    assert ticket.number is None and ticket.code is None


def test_register_emits_ticket_registered_event():
    ticket = _register(evidences=[VisualEvidence("error.png", "image/png", PNG)])
    events = ticket.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], TicketRegistered)
    assert events[0].ticket_id == ticket.id and events[0].has_evidence is True
    assert ticket.pull_events() == []


@pytest.mark.parametrize("field", ["title", "description"])
def test_register_rejects_missing_required_data(field):
    with pytest.raises(InvalidTicketDataError):
        _register(**{field: "   "})


def test_register_rejects_too_long_title():
    with pytest.raises(InvalidTicketDataError):
        _register(title="x" * 201)


def test_evidence_rejects_unsupported_format():
    with pytest.raises(InvalidVisualEvidenceError):
        VisualEvidence("error.gif", "image/gif", PNG)


def test_evidence_rejects_files_over_10_mb():
    with pytest.raises(InvalidVisualEvidenceError):
        VisualEvidence("error.png", "image/png", b"0" * (MAX_EVIDENCE_BYTES + 1))


def test_code_uses_four_digit_format():
    ticket = _register()
    ticket.number = 7
    assert ticket.code == "TK-0007"


def test_add_comment_rejects_empty_content():
    ticket = _register()
    with pytest.raises(InvalidTicketDataError):
        ticket.add_comment(author_id=uuid.uuid4(), content=" ")
