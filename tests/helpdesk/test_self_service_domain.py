"""Pruebas unitarias de US12 / T76: dominio Helpdesk, TriageDiagnosis.reopen_for_analyst_review, ACL y auditoría."""
import uuid
from unittest.mock import MagicMock

import pytest

from app.analytics.application.audit_log_service import AuditEventHandler
from app.helpdesk.application.ports import (
    ISelfServiceRecommendationReader,
    SelfServiceRecommendation,
    SelfServiceSource,
)
from app.helpdesk.application.status_change_policy import Actor
from app.helpdesk.application.ticket_query_service import TicketQueryService
from app.helpdesk.domain.enums import ImpactLevel, SupportTier, TicketStatus
from app.helpdesk.domain.events import SelfServiceAccepted, SelfServiceRejected, TicketStatusChanged
from app.helpdesk.domain.exceptions import (
    InvalidTicketDataError,
    InvalidTicketStateTransitionError,
    TicketStatusChangeForbiddenError,
)
from app.helpdesk.domain.ticket import MAX_REASON_LENGTH, Ticket
from app.shared.infrastructure.pii_masker import RegexSpacyPiiMasker
from app.smart_triage.domain.triage_diagnosis import ReviewDecision, ReviewStatus
from app.smart_triage.infrastructure.self_service_rejection_handler import SelfServiceRejectionHandler
from tests.smart_triage.test_triage_diagnosis import _diagnosis, evaluate

S = TicketStatus
_MASKER = RegexSpacyPiiMasker("clave-unitaria-us12-sello-pii-0123456789", spacy_model=None)


def _ticket(status: TicketStatus = S.SELF_SERVICE_PROPOSED) -> Ticket:
    ticket = Ticket.register(
        workspace_id=uuid.uuid4(),
        reporter_id=uuid.uuid4(),
        title="Error VPN 809",
        description="No conecta la VPN desde casa",
        impact_level=ImpactLevel.MEDIUM,
    )
    ticket.pull_events()
    ticket.status = status
    if status is S.SELF_SERVICE_PROPOSED:
        ticket.current_tier = SupportTier.SELF_SERVICE
    elif status in (S.PENDING_ASSIGNMENT, S.ASSIGNED_L1):
        ticket.current_tier = SupportTier.TIER_L1
    return ticket


# --- Dominio Helpdesk: accept_self_service y reject_self_service ---------------------------------------------


def test_accept_self_service_resolves_ticket_keeping_self_service_tier():
    ticket = _ticket(S.SELF_SERVICE_PROPOSED)
    ticket.accept_self_service(reporter_id=ticket.reporter_id)

    assert ticket.status is S.RESOLVED
    assert ticket.current_tier is SupportTier.SELF_SERVICE
    assert ticket.resolved_at is not None
    assert len(ticket.status_history) == 1
    entry = ticket.status_history[0]
    assert entry.previous_status is S.SELF_SERVICE_PROPOSED
    assert entry.new_status is S.RESOLVED
    assert entry.changed_by == ticket.reporter_id

    events = ticket.pull_events()
    assert [type(e) for e in events] == [TicketStatusChanged, SelfServiceAccepted]
    accepted = events[1]
    assert accepted.ticket_id == ticket.id
    assert accepted.workspace_id == ticket.workspace_id
    assert accepted.reporter_id == ticket.reporter_id


def test_reject_self_service_routes_to_pending_assignment_l1_and_emits_event():
    ticket = _ticket(S.SELF_SERVICE_PROPOSED)
    ticket.reject_self_service(reporter_id=ticket.reporter_id, reason="  Sigue apareciendo el error 809.  ")

    assert ticket.status is S.PENDING_ASSIGNMENT
    assert ticket.current_tier is SupportTier.TIER_L1
    assert ticket.assigned_analyst_id is None
    assert ticket.resolved_at is None
    entry = ticket.status_history[-1]
    assert entry.previous_status is S.SELF_SERVICE_PROPOSED
    assert entry.new_status is S.PENDING_ASSIGNMENT
    assert entry.reason == "Sigue apareciendo el error 809."

    events = ticket.pull_events()
    assert [type(e) for e in events] == [TicketStatusChanged, SelfServiceRejected]
    assert events[1].reason == "Sigue apareciendo el error 809."


@pytest.mark.parametrize("raw_reason", [None, "", "   \t\n  "])
def test_reject_self_service_normalizes_blank_reason_to_none_and_uses_default_in_history(raw_reason):
    ticket = _ticket(S.SELF_SERVICE_PROPOSED)
    ticket.reject_self_service(reporter_id=ticket.reporter_id, reason=raw_reason)

    assert ticket.status_history[-1].reason is not None
    assert "autoservicio" in ticket.status_history[-1].reason.lower()
    events = ticket.pull_events()
    assert isinstance(events[1], SelfServiceRejected)
    assert events[1].reason is None


def test_self_service_methods_reject_non_reporter_before_state_check():
    ticket = _ticket(S.PENDING_ASSIGNMENT)
    stranger = uuid.uuid4()

    with pytest.raises(TicketStatusChangeForbiddenError):
        ticket.accept_self_service(reporter_id=stranger)
    with pytest.raises(TicketStatusChangeForbiddenError):
        ticket.reject_self_service(reporter_id=stranger, reason="No funciona")


@pytest.mark.parametrize(
    "status",
    [S.OPEN, S.PENDING_ASSIGNMENT, S.ASSIGNED_L1, S.ESCALATED_L2, S.RESOLVED, S.CLOSED, S.REOPENED],
)
def test_self_service_methods_require_self_service_proposed_status(status):
    ticket = _ticket(status)

    with pytest.raises(InvalidTicketStateTransitionError):
        ticket.accept_self_service(reporter_id=ticket.reporter_id)
    with pytest.raises(InvalidTicketStateTransitionError):
        ticket.reject_self_service(reporter_id=ticket.reporter_id)


def test_reject_self_service_enforces_max_reason_length():
    ticket = _ticket(S.SELF_SERVICE_PROPOSED)
    with pytest.raises(InvalidTicketDataError):
        ticket.reject_self_service(reporter_id=ticket.reporter_id, reason="x" * (MAX_REASON_LENGTH + 1))


# --- Dominio Smart Triage: reopen_for_analyst_review (D10) ---------------------------------------------------


def test_reopen_for_analyst_review_transitions_self_service_proposed_to_pending_review_idempotently():
    diagnosis = _diagnosis(evaluate(0.91))
    assert diagnosis.review_status is ReviewStatus.SELF_SERVICE_PROPOSED
    assert not diagnosis.can_review(ReviewDecision.APPROVE)

    assert diagnosis.reopen_for_analyst_review() is True
    assert diagnosis.review_status is ReviewStatus.PENDING_REVIEW
    assert diagnosis.can_review(ReviewDecision.APPROVE)
    assert diagnosis.can_review(ReviewDecision.EDIT_AND_APPROVE)
    assert diagnosis.can_review(ReviewDecision.REJECT)
    assert diagnosis.can_review(ReviewDecision.MANUAL_RESPONSE)

    # Idempotente: segunda invocación no vuelve a modificar
    assert diagnosis.reopen_for_analyst_review() is False
    assert diagnosis.review_status is ReviewStatus.PENDING_REVIEW


@pytest.mark.parametrize(
    "initial_status",
    [
        ReviewStatus.PENDING_REVIEW,
        ReviewStatus.NOT_APPLICABLE,
        ReviewStatus.APPROVED,
        ReviewStatus.EDITED_AND_APPROVED,
        ReviewStatus.REJECTED,
        ReviewStatus.MANUAL_RESPONSE,
    ],
)
def test_reopen_for_analyst_review_ignores_other_review_statuses(initial_status):
    diagnosis = _diagnosis(evaluate(0.75))
    diagnosis.review_status = initial_status

    assert diagnosis.reopen_for_analyst_review() is False
    assert diagnosis.review_status is initial_status


# --- Aplicación Helpdesk: TicketQueryService solo consulta ACL en SELF_SERVICE_PROPOSED ----------------------


class _StubReader(ISelfServiceRecommendationReader):
    def __init__(self, rec: SelfServiceRecommendation | None) -> None:
        self._rec = rec
        self.calls: list[uuid.UUID] = []

    def for_ticket(self, ticket_id: uuid.UUID) -> SelfServiceRecommendation | None:
        self.calls.append(ticket_id)
        return self._rec


def test_ticket_query_service_reads_recommendation_only_in_self_service_proposed():
    rec = SelfServiceRecommendation(
        summary="Cambia el protocolo a IKEv2.",
        steps=("Abre VPN.", "Selecciona IKEv2."),
        match_percentage=89,
        confidence_label="Alta coincidencia",
        sources=(SelfServiceSource(reference="F1", document_title="Manual VPN", citation="guia-vpn.md, párr. 1"),),
    )

    for status in (S.SELF_SERVICE_PROPOSED, S.PENDING_ASSIGNMENT, S.RESOLVED):
        ticket = _ticket(status)
        tickets_repo = MagicMock()
        tickets_repo.find_by_id.return_value = ticket
        users = MagicMock()
        users.display_names.return_value = {ticket.reporter_id: "Colaborador"}
        reader = _StubReader(rec)

        service = TicketQueryService(
            read_model=MagicMock(), tickets=tickets_repo, users=users, self_service_reader=reader
        )
        actor = Actor(id=ticket.reporter_id, workspace_id=ticket.workspace_id, permissions=frozenset())
        detail = service.detail(actor, ticket.id)

        if status is S.SELF_SERVICE_PROPOSED:
            assert reader.calls == [ticket.id]
            assert detail.self_service_recommendation == rec
        else:
            assert reader.calls == []
            assert detail.self_service_recommendation is None


# --- Auditoría: SelfServiceAccepted y SelfServiceRejected ----------------------------------------------------


def test_audit_handler_maps_self_service_accepted_and_rejected_with_pii_masking():
    handler = AuditEventHandler(masker=_MASKER)
    ws_id, ticket_id, reporter_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    accepted = handler.to_audit_entry(
        SelfServiceAccepted(ticket_id=ticket_id, workspace_id=ws_id, reporter_id=reporter_id)
    )
    assert accepted is not None
    assert accepted.event_type == "SelfServiceAccepted"
    assert accepted.actor_id == reporter_id
    assert accepted.entity_type == "ticket"
    assert accepted.entity_id == ticket_id
    assert accepted.ticket_id == ticket_id
    assert accepted.detail == {"outcome": "RESOLVED_BY_SELF_SERVICE"}
    assert accepted.verify_integrity()

    rejected = handler.to_audit_entry(
        SelfServiceRejected(
            ticket_id=ticket_id,
            workspace_id=ws_id,
            reporter_id=reporter_id,
            reason="Sigue fallando para ana.perez@empresa.pe desde 10.20.30.40",
        )
    )
    assert rejected is not None
    assert rejected.event_type == "SelfServiceRejected"
    assert rejected.actor_id == reporter_id
    assert rejected.entity_type == "ticket"
    assert rejected.entity_id == ticket_id
    assert rejected.detail["outcome"] == "DERIVED_TO_ANALYST"
    assert "ana.perez@empresa.pe" not in rejected.detail["reason"]
    assert "10.20.30.40" not in rejected.detail["reason"]
    assert rejected.verify_integrity()

    rejected_no_reason = handler.to_audit_entry(
        SelfServiceRejected(ticket_id=ticket_id, workspace_id=ws_id, reporter_id=reporter_id, reason=None)
    )
    assert rejected_no_reason is not None
    assert rejected_no_reason.detail == {"outcome": "DERIVED_TO_ANALYST", "reason": None}


def test_self_service_rejection_handler_ignores_unrelated_status_transitions_without_opening_session():
    factory = MagicMock()
    handler = SelfServiceRejectionHandler(session_factory=factory)

    unrelated = TicketStatusChanged(
        ticket_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        reporter_id=uuid.uuid4(),
        previous_status="SELF_SERVICE_PROPOSED",
        new_status="RESOLVED",
        changed_by=uuid.uuid4(),
    )
    assert handler(unrelated) is False
    factory.assert_not_called()

