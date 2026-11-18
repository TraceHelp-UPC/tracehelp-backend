"""Steps de las features de revisión HITL y endpoints de diagnóstico (T38, US15 y T40, TS07)."""
import uuid

from behave import given, then, when

from app.helpdesk.domain.enums import ImpactLevel, TicketStatus
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.smart_triage.domain.diagnosis import DiagnosisStatus
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)
from tests.smart_triage.test_triage_diagnosis import _diagnosis, evaluate


def _headers(context, role: str) -> dict:
    user = SqlAlchemyUserRepository(context.session).find_by_id(context.users[role].id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _create_triaged_ticket(
    context,
    *,
    ticket_status: TicketStatus = TicketStatus.ASSIGNED_L1,
    score: float = 0.78,
    outcome: DiagnosisStatus = DiagnosisStatus.ANSWERED,
    with_diagnosis: bool = True,
):
    ticket = Ticket.register(
        workspace_id=context.workspace.id,
        reporter_id=context.users["COLLABORATOR"].id,
        title="VPN error 809",
        description="No conecta la VPN desde casa",
        impact_level=ImpactLevel.MEDIUM,
    )
    ticket.status = ticket_status
    if ticket_status in {TicketStatus.ASSIGNED_L1, TicketStatus.ESCALATED_L2, TicketStatus.RESOLVED}:
        ticket.assigned_analyst_id = context.users["ANALYST_L1"].id
    SqlAlchemyTicketRepository(context.session).save(ticket)
    context.hitl_ticket = ticket
    context.hitl_diagnosis = None
    if with_diagnosis:
        diag = _diagnosis(evaluate(score), status=outcome)
        diag.ticket_id = ticket.id
        diag.workspace_id = context.workspace.id
        diag.pull_events()
        SqlAlchemyTriageDiagnosisRepository(context.session).save(diag)
        context.hitl_diagnosis = diag
    context.session.commit()


@given('a triaged ticket in status "{status}" with a pending AI diagnosis')
def step_triaged_ticket(context, status):
    _create_triaged_ticket(context, ticket_status=TicketStatus(status), score=0.78)


@given("a triaged ticket with a self-service proposal")
def step_self_service_ticket(context):
    _create_triaged_ticket(context, ticket_status=TicketStatus.SELF_SERVICE_PROPOSED, score=0.91)


@given("a ticket that is still waiting for automatic triage")
def step_untriaged_ticket(context):
    _create_triaged_ticket(context, ticket_status=TicketStatus.OPEN, with_diagnosis=False)


@when('the "{role}" reviews the diagnosis with decision "{decision}"')
def step_review_decision(context, role, decision):
    context.response = context.client.post(
        f"/api/v1/triage/diagnoses/{context.hitl_diagnosis.id}/review",
        json={"decision": decision},
        headers=_headers(context, role),
    )


@when('the "{role}" edits and approves the diagnosis with summary "{summary}" and step "{step_text}"')
def step_edit_and_approve(context, role, summary, step_text):
    context.response = context.client.post(
        f"/api/v1/triage/diagnoses/{context.hitl_diagnosis.id}/review",
        json={"decision": "EDIT_AND_APPROVE", "summary": summary, "steps": [step_text]},
        headers=_headers(context, role),
    )


@when('the "{role}" rejects the diagnosis with reason "{reason}"')
def step_reject_diagnosis(context, role, reason):
    context.response = context.client.post(
        f"/api/v1/triage/diagnoses/{context.hitl_diagnosis.id}/review",
        json={"decision": "REJECT", "reason": reason},
        headers=_headers(context, role),
    )


@when('the "{role}" responds manually to the diagnosis with "{response_text}"')
def step_manual_response(context, role, response_text):
    context.response = context.client.post(
        f"/api/v1/triage/diagnoses/{context.hitl_diagnosis.id}/review",
        json={"decision": "MANUAL_RESPONSE", "response": response_text},
        headers=_headers(context, role),
    )


@when('the "{role}" requests the diagnosis of the ticket')
def step_get_diagnosis(context, role):
    context.response = context.client.get(
        f"/api/v1/tickets/{context.hitl_ticket.id}/diagnosis",
        headers=_headers(context, role),
    )


@when("an anonymous user requests the diagnosis of the ticket")
def step_get_diagnosis_anonymous(context):
    context.response = context.client.get(f"/api/v1/tickets/{context.hitl_ticket.id}/diagnosis")


@when('the "{role}" reviews a nonexistent diagnosis')
def step_review_unknown_diagnosis(context, role):
    context.response = context.client.post(
        f"/api/v1/triage/diagnoses/{uuid.uuid4()}/review",
        json={"decision": "APPROVE"},
        headers=_headers(context, role),
    )


@then('the review resolves the ticket with status "{review_status}"')
def step_review_resolves(context, review_status):
    body = context.response.json()
    assert body["ticket_resolved"] is True, body
    assert body["diagnosis"]["review_status"] == review_status, body
    assert body["diagnosis"]["ticket_status"] == "RESOLVED", body


@then('the review does not resolve the ticket and leaves diagnosis in "{review_status}"')
def step_review_does_not_resolve(context, review_status):
    body = context.response.json()
    assert body["ticket_resolved"] is False, body
    assert body["diagnosis"]["review_status"] == review_status, body
    assert body["diagnosis"]["ticket_status"] == "ASSIGNED_L1", body


@then('the ticket has a visible comment starting with "{prefix}"')
def step_ticket_visible_comment(context, prefix):
    context.session.expire_all()
    ticket = SqlAlchemyTicketRepository(context.session).find_by_id(context.hitl_ticket.id)
    visible = [c for c in ticket.comments if not c.is_internal_note]
    assert visible and visible[-1].content.startswith(prefix), [c.content for c in visible]


@then('the audit log records an "{event_type}" event with decision "{decision}"')
def step_audit_log_review_event(context, event_type, decision):
    resp = context.client.get(
        f"/api/v1/audit-log?event_type={event_type}&ticket_id={context.hitl_ticket.id}",
        headers=_headers(context, "IT_LEADER"),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert items and items[0]["detail"]["decision"] == decision, items


@then('the diagnosis response has review status "{review_status}"')
def step_diagnosis_response_status(context, review_status):
    body = context.response.json()
    assert body["review_status"] == review_status, body


@then("the diagnosis response hides internal similarity scores and OCR details")
def step_diagnosis_hides_internal_details(context):
    body = context.response.json()
    assert body["confidence_score"] is None and body["ocr"] is None, body
    assert body["ai_answer"]["sources"][0]["similarity"] is None, body
