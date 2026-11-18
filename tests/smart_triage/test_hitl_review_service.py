"""Pruebas de integración de la revisión HITL (T35). Requieren TEST_DATABASE_URL.

Comprueban que el diagnóstico y el ticket cambian juntos, en una sola transacción, y que si el ticket no puede
resolverse no se guarda nada.
"""
import uuid

import pytest

from app.helpdesk.domain.enums import ImpactLevel, TicketStatus
from app.helpdesk.domain.events import TicketStatusChanged
from app.helpdesk.domain.exceptions import InvalidTicketStateTransitionError, TicketStatusChangeForbiddenError
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.domain.permissions import RolePermission
from app.iam.infrastructure.persistence.models import UserModel
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.hitl_review_service import (
    DiagnosisNotFoundError,
    HitlPermissionError,
    ReviewDiagnosisCommand,
)
from app.smart_triage.application.ports import Reviewer
from app.smart_triage.domain.diagnosis import DiagnosisStatus
from app.smart_triage.domain.events import AiResolutionReviewed
from app.smart_triage.domain.triage_diagnosis import DiagnosisAlreadyReviewedError, ReviewDecision, ReviewStatus
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)
from app.smart_triage.interfaces.rest.dependencies import build_hitl_review_service
from tests.conftest import FAKE_HASH
from tests.smart_triage.test_triage_diagnosis import _diagnosis, evaluate


def _reviewer(user: UserModel) -> Reviewer:
    permissions = frozenset(p.value for p in RolePermission.for_role(RoleName(user.role)).permissions)
    return Reviewer(id=user.id, workspace_id=user.workspace_id, permissions=permissions)


@pytest.fixture()
def hitl(db_session, workspace_and_users):
    workspace, collaborator, analyst = workspace_and_users
    specialist = UserModel(
        id=uuid.uuid4(), workspace_id=workspace.id, full_name="Especialista Demo",
        email=f"esp-{uuid.uuid4().hex[:6]}@demo.pe", password_hash=FAKE_HASH, role=RoleName.SPECIALIST_L2, department="TI",
    )
    db_session.add(specialist)
    db_session.flush()
    bus = InMemoryEventBus()
    events: list = []
    bus.subscribe(AiResolutionReviewed, events.append)
    bus.subscribe(TicketStatusChanged, events.append)

    def setup(ticket_status=TicketStatus.ASSIGNED_L1, outcome=DiagnosisStatus.ANSWERED):
        ticket = Ticket.register(
            workspace_id=workspace.id, reporter_id=collaborator.id, title="VPN error 809",
            description="No conecta la VPN desde casa", impact_level=ImpactLevel.MEDIUM,
        )
        ticket.status = ticket_status
        ticket.assigned_analyst_id = analyst.id if ticket_status is not TicketStatus.PENDING_ASSIGNMENT else None
        SqlAlchemyTicketRepository(db_session).save(ticket)
        diagnosis = _diagnosis(evaluate(0.78), status=outcome)
        diagnosis.ticket_id, diagnosis.workspace_id = ticket.id, workspace.id
        diagnosis.pull_events()
        SqlAlchemyTriageDiagnosisRepository(db_session).save(diagnosis)
        db_session.commit()  # el rollback del servicio no debe borrar la preparación de la prueba
        return ticket, diagnosis

    def review(diagnosis, user, decision, **kwargs):
        service = build_hitl_review_service(db_session, bus)
        return service.review(ReviewDiagnosisCommand(diagnosis.id, _reviewer(user), decision, **kwargs))

    def review_as(diagnosis_id, reviewer, decision, **kwargs):
        service = build_hitl_review_service(db_session, bus)
        return service.review(ReviewDiagnosisCommand(diagnosis_id, reviewer, decision, **kwargs))

    def reload(ticket, diagnosis):
        db_session.expire_all()
        return (
            SqlAlchemyTicketRepository(db_session).find_by_id(ticket.id),
            SqlAlchemyTriageDiagnosisRepository(db_session).find_by_id(diagnosis.id),
        )

    return {
        "setup": setup, "review": review, "review_as": review_as, "reload": reload, "events": events,
        "analyst": analyst, "specialist": specialist, "collaborator": collaborator,
    }


def test_approving_resolves_the_ticket_with_the_ai_answer(hitl):
    ticket, diagnosis = hitl["setup"]()
    result = hitl["review"](diagnosis, hitl["analyst"], ReviewDecision.APPROVE)

    assert result.ticket_resolved
    ticket, stored = hitl["reload"](ticket, diagnosis)
    assert stored.review_status is ReviewStatus.APPROVED and stored.reviewed_by == hitl["analyst"].id
    assert ticket.status is TicketStatus.RESOLVED and ticket.resolved_at is not None
    [comment] = ticket.comments
    assert comment.is_ai_generated and not comment.is_internal_note
    assert comment.content.startswith("Puertos bloqueados [F1].") and "Fuentes: [F1]" in comment.content
    assert [type(e).__name__ for e in hitl["events"]] == ["AiResolutionReviewed", "TicketStatusChanged"]
    assert hitl["events"][1].changed_by == hitl["analyst"].id


def test_edited_answer_is_the_one_the_collaborator_receives(hitl):
    ticket, diagnosis = hitl["setup"]()
    hitl["review"](
        diagnosis, hitl["analyst"], ReviewDecision.EDIT_AND_APPROVE,
        summary="Tu router bloquea la VPN.", steps=("Reinicia el router.", "Si sigue, usa los datos del celular."),
    )
    ticket, stored = hitl["reload"](ticket, diagnosis)
    assert stored.review_status is ReviewStatus.EDITED_AND_APPROVED
    assert stored.final_steps == ("Reinicia el router.", "Si sigue, usa los datos del celular.")
    assert ticket.comments[0].content.startswith("Tu router bloquea la VPN.\n\n1. Reinicia el router.")


def test_rejecting_keeps_the_ticket_with_the_analyst(hitl):
    ticket, diagnosis = hitl["setup"]()
    result = hitl["review"](diagnosis, hitl["analyst"], ReviewDecision.REJECT, reason="No aplica a esta versión")
    assert not result.ticket_resolved
    ticket, stored = hitl["reload"](ticket, diagnosis)
    assert stored.review_status is ReviewStatus.REJECTED and ticket.status is TicketStatus.ASSIGNED_L1
    assert ticket.comments == []
    assert [type(e).__name__ for e in hitl["events"]] == ["AiResolutionReviewed"]


def test_manual_response_resolves_the_ticket(hitl):
    ticket, diagnosis = hitl["setup"](outcome=DiagnosisStatus.INSUFFICIENT_EVIDENCE)
    hitl["review"](diagnosis, hitl["analyst"], ReviewDecision.MANUAL_RESPONSE, response="Reinstalé tu perfil VPN; prueba otra vez.")
    ticket, stored = hitl["reload"](ticket, diagnosis)
    assert stored.review_status is ReviewStatus.MANUAL_RESPONSE and ticket.status is TicketStatus.RESOLVED
    assert ticket.comments[0].content == "Reinstalé tu perfil VPN; prueba otra vez."
    assert not ticket.comments[0].is_ai_generated


def test_ticket_not_taken_yet_blocks_the_review_and_saves_nothing(hitl):
    ticket, diagnosis = hitl["setup"](ticket_status=TicketStatus.PENDING_ASSIGNMENT)
    with pytest.raises(InvalidTicketStateTransitionError, match="Atender"):
        hitl["review"](diagnosis, hitl["analyst"], ReviewDecision.APPROVE)
    ticket, stored = hitl["reload"](ticket, diagnosis)
    assert stored.review_status is ReviewStatus.PENDING_REVIEW and stored.reviewed_at is None
    assert ticket.status is TicketStatus.PENDING_ASSIGNMENT and hitl["events"] == []


def test_escalated_tickets_are_resolved_by_the_specialist(hitl):
    ticket, diagnosis = hitl["setup"](ticket_status=TicketStatus.ESCALATED_L2)
    with pytest.raises(TicketStatusChangeForbiddenError):
        hitl["review"](diagnosis, hitl["analyst"], ReviewDecision.APPROVE)
    assert hitl["reload"](ticket, diagnosis)[1].review_status is ReviewStatus.PENDING_REVIEW

    hitl["review"](diagnosis, hitl["specialist"], ReviewDecision.APPROVE)
    ticket, stored = hitl["reload"](ticket, diagnosis)
    assert stored.review_status is ReviewStatus.APPROVED and ticket.status is TicketStatus.RESOLVED


def test_a_diagnosis_is_reviewed_only_once(hitl):
    _, diagnosis = hitl["setup"]()
    hitl["review"](diagnosis, hitl["analyst"], ReviewDecision.APPROVE)
    with pytest.raises(DiagnosisAlreadyReviewedError):
        hitl["review"](diagnosis, hitl["specialist"], ReviewDecision.APPROVE)


def test_collaborators_cannot_review(hitl):
    _, diagnosis = hitl["setup"]()
    with pytest.raises(HitlPermissionError):
        hitl["review"](diagnosis, hitl["collaborator"], ReviewDecision.APPROVE)


def test_unknown_or_foreign_diagnoses_are_not_found(hitl):
    _, diagnosis = hitl["setup"]()
    outsider = Reviewer(id=uuid.uuid4(), workspace_id=uuid.uuid4(), permissions=frozenset({"triage:validate_hitl"}))
    with pytest.raises(DiagnosisNotFoundError):
        hitl["review_as"](diagnosis.id, outsider, ReviewDecision.APPROVE)
    with pytest.raises(DiagnosisNotFoundError):
        hitl["review_as"](uuid.uuid4(), _reviewer(hitl["analyst"]), ReviewDecision.APPROVE)
