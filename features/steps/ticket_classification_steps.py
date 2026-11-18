"""Steps de la feature de clasificación en el triaje y corrección por el analista (T43, US27)."""
from behave import then, when

from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)


def _headers(context, role: str) -> dict:
    user = SqlAlchemyUserRepository(context.session).find_by_id(context.users[role].id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


@when(
    'the "{role}" corrects the classification of the ticket to category "{category}" and priority "{priority}" with reason "{reason}"'
)
def step_correct_classification(context, role, category, priority, reason):
    context.response = context.client.patch(
        f"/api/v1/tickets/{context.triage_ticket.id}/classification",
        json={"category": category, "priority": priority, "reason": reason},
        headers=_headers(context, role),
    )


@then('the ticket has category "{category}" and priority "{priority}"')
def step_ticket_category_priority(context, category, priority):
    context.session.expire_all()
    ticket = SqlAlchemyTicketRepository(context.session).find_by_id(context.triage_ticket.id)
    actual_cat = ticket.category.value if ticket.category else None
    assert (actual_cat, ticket.priority.value) == (category, priority), (actual_cat, ticket.priority.value)


@then("the ticket has no category assigned")
def step_ticket_no_category(context):
    context.session.expire_all()
    ticket = SqlAlchemyTicketRepository(context.session).find_by_id(context.triage_ticket.id)
    assert ticket.category is None, ticket.category


@then('the diagnosis of the ticket suggests category "{category}" and priority "{priority}"')
def step_diagnosis_suggestion(context, category, priority):
    diagnosis = SqlAlchemyTriageDiagnosisRepository(context.session).find_by_ticket_id(context.triage_ticket.id)
    cat = diagnosis.suggested_category.value if diagnosis.suggested_category else None
    prio = diagnosis.suggested_priority.value if diagnosis.suggested_priority else None
    assert (cat, prio) == (category, priority), (cat, prio)


@then("the diagnosis of the ticket has no suggested category")
def step_diagnosis_no_suggestion(context):
    diagnosis = SqlAlchemyTriageDiagnosisRepository(context.session).find_by_ticket_id(context.triage_ticket.id)
    assert diagnosis.suggested_category is None and diagnosis.suggested_priority is None


@then(
    'the audit log records a "{event_type}" event for the ticket with previous category "{prev_cat}" and new category "{new_cat}"'
)
def step_audit_log_records_correction(context, event_type, prev_cat, new_cat):
    response = context.client.get(
        f"/api/v1/audit-log?event_type={event_type}&ticket_id={context.triage_ticket.id}",
        headers=_headers(context, "IT_LEADER"),
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1, items
    detail = items[0]["detail"]
    assert detail["previous_category"] == prev_cat and detail["new_category"] == new_cat, detail
