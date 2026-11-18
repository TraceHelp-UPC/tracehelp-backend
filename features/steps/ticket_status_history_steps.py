"""Steps de la feature de historial de cambios de estado del ticket (T46, US14)."""
import uuid

from behave import then, when

from app.helpdesk.domain.enums import TicketStatus
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider


def _headers(context, user_model) -> dict:
    user = SqlAlchemyUserRepository(context.session).find_by_id(user_model.id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


@when('the automatic triage routes the ticket to "{status}" with reason "{reason}"')
def step_system_routes_ticket(context, status, reason):
    repo = SqlAlchemyTicketRepository(context.session)
    ticket = repo.find_by_id(context.ticket_id)
    ticket.change_status(TicketStatus(status), changed_by=None, reason=reason)
    repo.save(ticket)
    context.session.flush()


@when('the "{role}" changes the ticket status to "{status}" with reason "{reason}"')
def step_change_status_with_reason(context, role, status, reason):
    context.response = context.client.patch(
        f"/api/v1/tickets/{context.ticket_id}/status",
        json={"status": status, "reason": reason},
        headers=_headers(context, context.users[role]),
    )
    assert context.response.status_code == 200, context.response.text


@when('the "{role}" requests the status history of the ticket')
def step_request_history(context, role):
    context.response = context.client.get(
        f"/api/v1/tickets/{context.ticket_id}/history",
        headers=_headers(context, context.users[role]),
    )


@when("the other collaborator requests the status history of the ticket")
def step_other_requests_history(context):
    context.response = context.client.get(
        f"/api/v1/tickets/{context.ticket_id}/history",
        headers=_headers(context, context.other_collaborator),
    )


@when('the "{role}" requests the status history of a nonexistent ticket')
def step_request_unknown_history(context, role):
    context.response = context.client.get(
        f"/api/v1/tickets/{uuid.uuid4()}/history",
        headers=_headers(context, context.users[role]),
    )


@then("the status history shows these transitions in chronological order:")
def step_verify_status_history(context):
    items = context.response.json()["items"]
    expected = [
        (
            row["previous_status"].strip(),
            row["new_status"].strip(),
            row["changed_by_name"].strip(),
            row["reason"].strip(),
        )
        for row in context.table
    ]
    actual = [(i["previous_status"], i["new_status"], i["changed_by_name"], i["reason"] or "") for i in items]
    assert actual == expected, f"Se esperaba {expected} y se obtuvo {actual}"
