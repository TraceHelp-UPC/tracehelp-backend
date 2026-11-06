"""Steps de las features de Smart Triage: diagnóstico RAG (US11), validación HITL (US15) y endpoints (TS07)."""
from behave import given, then, when

from app.analytics.infrastructure.persistence.audit_trail_repository import SqlAlchemyAuditTrailRepository
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.shared.infrastructure.event_bus import event_bus
from app.smart_triage.application.triage_service import EvaluateRagDiagnosisCommand, TriageService
from app.smart_triage.domain.value_objects import SourceCitation
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)


def _token(context, role: str) -> str:
    user = SqlAlchemyUserRepository(context.session).find_by_id(context.users[role].id)
    token, _ = get_token_provider().issue_access_token(user)
    return token


def _triage_service(context) -> TriageService:
    return TriageService(
        session=context.session,
        diagnoses=SqlAlchemyTriageDiagnosisRepository(context.session),
        tickets=SqlAlchemyTicketRepository(context.session),
        audit_logs=SqlAlchemyAuditTrailRepository(context.session),
        events=event_bus,
    )


@given(
    'the RAG engine retrieves chunk "{source_file}" page {page:d} paragraph {paragraph:d} with similarity {score:f} for the ticket'
)
def step_rag_retrieves_chunk(context, source_file, page, paragraph, score):
    citation = SourceCitation(
        source_file=source_file,
        page_number=page,
        paragraph_number=paragraph,
        similarity_score=score,
    )
    diagnosis = _triage_service(context).evaluate_rag_diagnosis(
        EvaluateRagDiagnosisCommand(
            workspace_id=context.workspace.id,
            ticket_id=context.ticket_id,
            query_text="No puedo ingresar al ERP",
            citations=[citation],
            synthesized_answer=f"Verificar configuración según {source_file} (pág. {page}, párr. {paragraph}).",
        )
    )
    context.diagnosis_id = diagnosis.id


@given("the RAG engine finds no relevant sources for the ticket")
def step_rag_finds_no_sources(context):
    diagnosis = _triage_service(context).evaluate_rag_diagnosis(
        EvaluateRagDiagnosisCommand(
            workspace_id=context.workspace.id,
            ticket_id=context.ticket_id,
            query_text="Fallo desconocido sin documentación",
            citations=[],
        )
    )
    context.diagnosis_id = diagnosis.id


@when('the "{role}" requests the ticket diagnosis')
def step_request_ticket_diagnosis(context, role):
    context.response = context.client.get(
        f"/api/v1/tickets/{context.ticket_id}/diagnosis",
        headers={"Authorization": f"Bearer {_token(context, role)}"},
    )


@when('the "{role}" reviews the diagnosis with action "{action}"')
def step_review_diagnosis_action(context, role, action):
    context.response = context.client.post(
        f"/api/v1/triage/diagnoses/{context.diagnosis_id}/review",
        json={"action": action},
        headers={"Authorization": f"Bearer {_token(context, role)}"},
    )


@when('the "{role}" submits edited text "{edited_text}" with review action "{action}"')
def step_review_diagnosis_with_text(context, role, edited_text, action):
    context.response = context.client.post(
        f"/api/v1/triage/diagnoses/{context.diagnosis_id}/review",
        json={"action": action, "edited_text": edited_text},
        headers={"Authorization": f"Bearer {_token(context, role)}"},
    )


@given('the "{role}" has already reviewed the diagnosis with action "{action}"')
def step_already_reviewed(context, role, action):
    resp = context.client.post(
        f"/api/v1/triage/diagnoses/{context.diagnosis_id}/review",
        json={"action": action},
        headers={"Authorization": f"Bearer {_token(context, role)}"},
    )
    assert resp.status_code == 200, resp.text


@then("the diagnosis has sufficient evidence with confidence {expected_score:f}")
def step_verify_sufficient_evidence(context, expected_score):
    body = context.response.json()
    assert body["has_sufficient_evidence"] is True
    assert body["is_low_confidence_alert"] is False
    assert abs(body["confidence_score"] - expected_score) < 1e-4
    assert body["suggested_text"] is not None


@then('the diagnosis includes citation "{source_file}" page {page:d} paragraph {paragraph:d}')
def step_verify_citation_included(context, source_file, page, paragraph):
    citations = context.response.json()["citations"]
    assert any(
        c["source_file"] == source_file and c["page_number"] == page and c["paragraph_number"] == paragraph
        for c in citations
    ), f"No se encontró la cita esperada en {citations}"


@then("the diagnosis reports insufficient evidence and low confidence alert")
def step_verify_insufficient_evidence(context):
    body = context.response.json()
    assert body["has_sufficient_evidence"] is False
    assert body["is_low_confidence_alert"] is True
    assert body["confidence_level"] == "INSUFFICIENT_EVIDENCE"
    assert body["suggested_text"] is None


@then("the diagnosis is marked as low confidence alert with score {expected_score:f}")
def step_verify_low_confidence_alert(context, expected_score):
    body = context.response.json()
    assert body["has_sufficient_evidence"] is False
    assert body["is_low_confidence_alert"] is True
    assert body["confidence_level"] == "LOW_CONFIDENCE_ALERT"
    assert abs(body["confidence_score"] - expected_score) < 1e-4


@then('the diagnosis validation status is "{expected_status}"')
def step_verify_validation_status(context, expected_status):
    body = context.response.json()
    assert body["validation_status"] == expected_status, body


@then('the diagnosis final approved text is "{expected_text}"')
def step_verify_final_approved_text(context, expected_text):
    body = context.response.json()
    assert body["final_approved_text"] == expected_text, body


@then('the audit trail records action "{expected_action}" for the ticket')
def step_verify_audit_trail_action(context, expected_action):
    entries = SqlAlchemyAuditTrailRepository(context.session).find_by_ticket(
        context.ticket_id, context.workspace.id
    )
    assert any(e.action_type.value == expected_action and e.verify_integrity() for e in entries), (
        f"No se encontró {expected_action} en {[e.action_type.value for e in entries]}"
    )
