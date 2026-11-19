"""Steps BDD para US12 / T78: rama de autoservicio, accept/reject y cierre del hueco D10."""
import contextlib
import uuid

from behave import given, then, when

from app.helpdesk.domain.enums import ImpactLevel, SupportTier, TicketStatus
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.helpdesk.infrastructure.triage_routing import TriageRoutingHandler
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.automatic_triage_service import AutomaticTriageService
from app.smart_triage.application.diagnosis_generation_service import DiagnosisGenerationService
from app.smart_triage.application.evidence_retrieval_service import EvidenceRetrievalService
from app.smart_triage.application.triage_analysis_service import TriageAnalysisService
from app.smart_triage.domain.events import TriageCompleted
from app.smart_triage.domain.grounding import GroundingThresholds
from app.smart_triage.domain.triage_diagnosis import ReviewStatus
from app.smart_triage.infrastructure.helpdesk.helpdesk_ticket_reader import HelpdeskTicketReader
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)
from tests.smart_triage.test_diagnosis_generation_service import FakeGenerator
from tests.smart_triage.test_evidence_retrieval_service import FakeRetriever, masker
from tests.smart_triage.test_triage_analysis_service import FakeOcr
from tests.smart_triage.test_triage_diagnosis import _diagnosis, evaluate

FAKE_HASH = "$2b$04$abcdefghijklmnopqrstuuJ8Pn6R6qVqzLqL7vR0Qe2b7r6P9q5Gm"

INTERNAL_RECOMMENDATION_KEYS = {
    "similarity",
    "similarity_threshold",
    "self_service_threshold",
    "model",
    "ocr",
    "outcome_reason",
    "suggested_category",
    "suggested_priority",
    "review_status",
    "chunk_id",
    "document_id",
}


def _headers(context, user_model: UserModel) -> dict[str, str]:
    user = SqlAlchemyUserRepository(context.session).find_by_id(user_model.id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _actor_model(context, actor: str) -> UserModel:
    if actor == "OTHER_COLLABORATOR":
        return context.other_collaborator
    if actor == "FOREIGN_COLLABORATOR":
        return context.foreign_collaborator
    return context.users[actor]


def _setup_ticket_and_diagnosis(
    context,
    *,
    ticket_status: TicketStatus,
    review_status: ReviewStatus | None = None,
    score: float = 0.89,
    with_diagnosis: bool = True,
) -> None:
    ticket = Ticket.register(
        workspace_id=context.workspace.id,
        reporter_id=context.users["COLLABORATOR"].id,
        title="VPN error 809 al conectar desde casa",
        description="Al intentar conectar la VPN corporativa aparece error 809.",
        impact_level=ImpactLevel.MEDIUM,
    )
    ticket.pull_events()
    ticket.status = ticket_status
    if ticket_status in {TicketStatus.PENDING_ASSIGNMENT, TicketStatus.ASSIGNED_L1}:
        ticket.current_tier = SupportTier.TIER_L1
    if ticket_status is TicketStatus.ASSIGNED_L1:
        ticket.assigned_analyst_id = context.users["ANALYST_L1"].id
    SqlAlchemyTicketRepository(context.session).save(ticket)
    context.ss_ticket = ticket
    context.ss_diagnosis = None

    if with_diagnosis:
        diag = _diagnosis(evaluate(score))
        diag.ticket_id = ticket.id
        diag.workspace_id = context.workspace.id
        if review_status is not None:
            diag.review_status = review_status
        diag.pull_events()
        SqlAlchemyTriageDiagnosisRepository(context.session).save(diag)
        context.ss_diagnosis = diag

    context.session.commit()


# --- Given -----------------------------------------------------------------------------------------------------


@given('a newly registered ticket "{title}" waiting for automatic triage')
def step_newly_registered_ticket(context, title: str):
    ticket = Ticket.register(
        workspace_id=context.workspace.id,
        reporter_id=context.users["COLLABORATOR"].id,
        title=title,
        description="Al intentar conectar la VPN corporativa aparece el error 809 en los puertos UDP.",
        impact_level=ImpactLevel.MEDIUM,
    )
    ticket.pull_events()
    SqlAlchemyTicketRepository(context.session).save(ticket)
    context.session.commit()
    context.ss_ticket = ticket
    context.ss_diagnosis = None


@given('a ticket in status "SELF_SERVICE_PROPOSED" with an eligible self-service diagnosis')
def step_ticket_in_self_service_proposed(context):
    _setup_ticket_and_diagnosis(
        context,
        ticket_status=TicketStatus.SELF_SERVICE_PROPOSED,
        review_status=ReviewStatus.SELF_SERVICE_PROPOSED,
        score=0.90,
    )


@given('a self-service setup with ticket status "{ticket_status}" and diagnosis review status "{review_status}"')
def step_custom_self_service_setup(context, ticket_status: str, review_status: str):
    _setup_ticket_and_diagnosis(
        context,
        ticket_status=TicketStatus(ticket_status),
        review_status=ReviewStatus(review_status),
        score=0.90,
    )


@given("a collaborator from another workspace")
def step_foreign_collaborator(context):
    other_ws = WorkspaceModel(id=uuid.uuid4(), name="Otra Empresa", subdomain=f"otra-{uuid.uuid4().hex[:6]}")
    context.session.add(other_ws)
    context.session.flush()
    user = UserModel(
        id=uuid.uuid4(),
        workspace_id=other_ws.id,
        full_name="Colaborador Externo",
        email=f"externo-{uuid.uuid4().hex[:6]}@otra.pe",
        password_hash=FAKE_HASH,
        role=RoleName.COLLABORATOR,
        department="TI",
    )
    context.session.add(user)
    context.session.commit()
    context.foreign_collaborator = user


# --- When ------------------------------------------------------------------------------------------------------


@when("automatic triage runs with similarity score {score:f} and self-service threshold {threshold:f}")
def step_run_triage_with_score(context, score: float, threshold: float):
    bus = InMemoryEventBus()
    bus.subscribe(
        TriageCompleted,
        TriageRoutingHandler(session_factory=lambda: contextlib.nullcontext(context.session), events=bus),
    )
    retrieval = EvidenceRetrievalService(
        retriever=FakeRetriever(score),
        masker=masker,
        events=bus,
        thresholds=GroundingThresholds(similarity=0.68, self_service=threshold),
    )
    service = AutomaticTriageService(
        session=context.session,
        tickets=HelpdeskTicketReader(context.session),
        diagnoses=SqlAlchemyTriageDiagnosisRepository(context.session),
        analysis=TriageAnalysisService(
            ocr=FakeOcr(),
            retrieval=retrieval,
            generation=DiagnosisGenerationService(generator=FakeGenerator(), masker=masker),
        ),
        masker=masker,
        events=bus,
    )
    context.ss_diagnosis = service.triage(context.ss_ticket.id)


@when('the "{role}" requests the detail of the self-service ticket')
def step_get_self_service_ticket_detail(context, role: str):
    context.response = context.client.get(
        f"/api/v1/tickets/{context.ss_ticket.id}",
        headers=_headers(context, _actor_model(context, role)),
    )


@when('the "{role}" requests the internal diagnosis of the self-service ticket')
def step_get_internal_diagnosis(context, role: str):
    context.response = context.client.get(
        f"/api/v1/tickets/{context.ss_ticket.id}/diagnosis",
        headers=_headers(context, _actor_model(context, role)),
    )


@when('the "{role}" accepts the self-service recommendation')
def step_accept_self_service(context, role: str):
    context.response = context.client.post(
        f"/api/v1/tickets/{context.ss_ticket.id}/self-service/accept",
        headers=_headers(context, _actor_model(context, role)),
    )


@when('the "{role}" rejects the self-service recommendation with reason "{reason}"')
def step_reject_self_service_with_reason(context, role: str, reason: str):
    context.response = context.client.post(
        f"/api/v1/tickets/{context.ss_ticket.id}/self-service/reject",
        json={"reason": reason},
        headers=_headers(context, _actor_model(context, role)),
    )


@when('the "{role}" rejects the self-service recommendation without a request body')
def step_reject_no_body(context, role: str):
    context.response = context.client.post(
        f"/api/v1/tickets/{context.ss_ticket.id}/self-service/reject",
        headers=_headers(context, _actor_model(context, role)),
    )


@when('the "{role}" rejects the self-service recommendation with an empty payload')
def step_reject_empty_payload(context, role: str):
    context.response = context.client.post(
        f"/api/v1/tickets/{context.ss_ticket.id}/self-service/reject",
        json={},
        headers=_headers(context, _actor_model(context, role)),
    )


@when('the "{role}" rejects the self-service recommendation with a blank reason')
def step_reject_blank_reason(context, role: str):
    context.response = context.client.post(
        f"/api/v1/tickets/{context.ss_ticket.id}/self-service/reject",
        json={"reason": "   "},
        headers=_headers(context, _actor_model(context, role)),
    )


@when('the "{role}" rejects the self-service recommendation with a reason of {length:d} characters')
def step_reject_long_reason(context, role: str, length: int):
    context.response = context.client.post(
        f"/api/v1/tickets/{context.ss_ticket.id}/self-service/reject",
        json={"reason": "a" * length},
        headers=_headers(context, _actor_model(context, role)),
    )


@when('the "{role}" rejects the self-service recommendation with an unknown field')
def step_reject_unknown_field(context, role: str):
    context.response = context.client.post(
        f"/api/v1/tickets/{context.ss_ticket.id}/self-service/reject",
        json={"reason": "ok", "extra_field": True},
        headers=_headers(context, _actor_model(context, role)),
    )


@when('the actor "{actor}" calls self-service "{action}" on the ticket')
def step_actor_calls_self_service(context, actor: str, action: str):
    context.response = context.client.post(
        f"/api/v1/tickets/{context.ss_ticket.id}/self-service/{action}",
        headers=_headers(context, _actor_model(context, actor)),
    )


@when('the "{role}" calls self-service "{action}" on the ticket')
def step_role_calls_self_service(context, role: str, action: str):
    context.response = context.client.post(
        f"/api/v1/tickets/{context.ss_ticket.id}/self-service/{action}",
        headers=_headers(context, _actor_model(context, role)),
    )


@when('the "{target}" ticket receives a self-service "{action}" call')
def step_target_ticket_self_service(context, target: str, action: str):
    if target == "nonexistent":
        ticket_id = uuid.uuid4()
        headers = _headers(context, context.users["COLLABORATOR"])
    elif target == "foreign":
        ticket_id = context.ss_ticket.id
        headers = _headers(context, context.foreign_collaborator)
    else:
        raise AssertionError(f"Objetivo no soportado: {target}")
    context.response = context.client.post(
        f"/api/v1/tickets/{ticket_id}/self-service/{action}",
        headers=headers,
    )


@when('an anonymous user calls self-service "{action}" on the ticket')
def step_anonymous_self_service(context, action: str):
    context.response = context.client.post(f"/api/v1/tickets/{context.ss_ticket.id}/self-service/{action}")


@when('the "{role}" tries to approve the self-service diagnosis in HITL')
def step_analyst_tries_hitl_approve(context, role: str):
    context.response = context.client.post(
        f"/api/v1/triage/diagnoses/{context.ss_diagnosis.id}/review",
        json={"decision": "APPROVE"},
        headers=_headers(context, _actor_model(context, role)),
    )


@when('the "{role}" takes the self-service ticket and approves its diagnosis in HITL')
def step_analyst_takes_and_approves(context, role: str):
    headers = _headers(context, _actor_model(context, role))
    assign = context.client.post(
        f"/api/v1/tickets/{context.ss_ticket.id}/assign",
        json={},
        headers=headers,
    )
    assert assign.status_code == 200, assign.text
    context.response = context.client.post(
        f"/api/v1/triage/diagnoses/{context.ss_diagnosis.id}/review",
        json={"decision": "APPROVE"},
        headers=headers,
    )


# --- Then ------------------------------------------------------------------------------------------------------


@then('the self-service ticket is in status "{status}" and tier "{tier}"')
def step_check_stored_ticket_status_and_tier(context, status: str, tier: str):
    context.session.expire_all()
    ticket = SqlAlchemyTicketRepository(context.session).find_by_id(context.ss_ticket.id)
    assert ticket is not None
    assert ticket.status.value == status, ticket.status
    assert ticket.current_tier.value == tier, ticket.current_tier


@then('the ticket detail exposes a self-service recommendation with match percentage {pct:d} and label "{label}"')
def step_detail_exposes_recommendation(context, pct: int, label: str):
    rec = context.response.json()["self_service_recommendation"]
    assert rec is not None, context.response.text
    assert rec["summary"], rec
    assert rec["steps"], rec
    assert rec["match_percentage"] == pct, rec
    assert rec["confidence_label"] == label, rec
    assert rec["sources"], rec
    for src in rec["sources"]:
        assert set(src.keys()) == {"reference", "document_title", "citation"}, src


@then("the self-service recommendation hides internal triage fields")
def step_recommendation_hides_internal_fields(context):
    rec = context.response.json()["self_service_recommendation"]
    assert rec is not None
    assert set(rec.keys()) == {"summary", "steps", "match_percentage", "confidence_label", "sources"}, rec
    assert INTERNAL_RECOMMENDATION_KEYS.isdisjoint(rec.keys()), rec
    for src in rec["sources"]:
        assert INTERNAL_RECOMMENDATION_KEYS.isdisjoint(src.keys()), src


@then("the ticket detail has no self-service recommendation")
def step_detail_has_no_recommendation(context):
    body = context.response.json()
    assert "self_service_recommendation" in body, body
    assert body["self_service_recommendation"] is None, body


@then('the response ticket has status "{status}", tier "{tier}" and a resolution timestamp')
def step_response_ticket_resolved(context, status: str, tier: str):
    body = context.response.json()
    assert body["status"] == status, body
    assert body["current_tier"] == tier, body
    assert body["resolved_at"] is not None, body


@then('the response ticket has status "{status}", tier "{tier}" and no assigned analyst')
def step_response_ticket_derived(context, status: str, tier: str):
    body = context.response.json()
    assert body["status"] == status, body
    assert body["current_tier"] == tier, body
    assert body["assigned_analyst_id"] is None, body


@then('the self-service ticket history records the transition from "{prev_status}" to "{new_status}"')
def step_self_service_history_transition(context, prev_status: str, new_status: str):
    resp = context.client.get(
        f"/api/v1/tickets/{context.ss_ticket.id}/history",
        headers=_headers(context, context.users["COLLABORATOR"]),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert any(h["previous_status"] == prev_status and h["new_status"] == new_status for h in items), items


@then('the audit log records "{event_type}" for the self-service ticket with outcome "{outcome}"')
def step_audit_records_self_service_accepted(context, event_type: str, outcome: str):
    resp = context.client.get(
        f"/api/v1/audit/logs?ticket_id={context.ss_ticket.id}&event_type={event_type}",
        headers=_headers(context, context.users["IT_LEADER"]),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1, items
    assert items[0]["actor_id"] == str(context.users["COLLABORATOR"].id), items[0]
    assert items[0]["detail"]["outcome"] == outcome, items[0]


@then('the audit log records "SelfServiceRejected" for the self-service ticket with masked reason')
def step_audit_records_self_service_rejected_masked(context):
    resp = context.client.get(
        f"/api/v1/audit/logs?ticket_id={context.ss_ticket.id}&event_type=SelfServiceRejected",
        headers=_headers(context, context.users["IT_LEADER"]),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1, items
    detail = items[0]["detail"]
    assert detail["outcome"] == "DERIVED_TO_ANALYST", detail
    reason = detail.get("reason") or ""
    assert "carlos@empresa.pe" not in reason, reason
    assert "10.0.0.15" not in reason, reason


@then('the self-service diagnosis is in review status "{review_status}"')
def step_diagnosis_review_status(context, review_status: str):
    context.session.expire_all()
    diag = SqlAlchemyTriageDiagnosisRepository(context.session).find_by_ticket_id(context.ss_ticket.id)
    assert diag is not None
    assert diag.review_status.value == review_status, diag.review_status


@then('the HITL approval resolves the ticket with diagnosis status "{review_status}"')
def step_hitl_approval_resolved(context, review_status: str):
    body = context.response.json()
    assert body["ticket_resolved"] is True, body
    assert body["diagnosis"]["review_status"] == review_status, body
    assert body["diagnosis"]["ticket_status"] == "RESOLVED", body


@then("the OpenAPI document documents self-service endpoints and TicketDetailResponse recommendation")
def step_openapi_documents_self_service(context):
    spec = context.response.json()
    paths = spec["paths"]
    for suffix in ("accept", "reject"):
        path = f"/api/v1/tickets/{{ticket_id}}/self-service/{suffix}"
        assert path in paths, f"Falta ruta {path} en OpenAPI"
        op = paths[path]["post"]
        assert op.get("summary") and op.get("description"), op
        assert {"200", "401", "403", "404", "422"} <= set(op["responses"]), op["responses"]
        for code in ("403", "404", "422"):
            assert "application/problem+json" in op["responses"][code].get("content", {}), (path, code)
    detail_props = spec["components"]["schemas"]["TicketDetailResponse"]["properties"]
    assert "self_service_recommendation" in detail_props, detail_props
