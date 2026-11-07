"""Steps de la feature de consulta de tickets (T18, TS08)."""
import uuid
from datetime import UTC, datetime, timedelta

from behave import given, then, when

from app.helpdesk.domain.enums import ImpactLevel
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider

HISTORY_URL = "/api/v1/tickets/my-history"


def _headers_for(context, user_model) -> dict:
    user = SqlAlchemyUserRepository(context.session).find_by_id(user_model.id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _report(context, reporter, title: str, hours_ago: int) -> Ticket:
    ticket = Ticket.register(
        workspace_id=context.workspace.id,
        reporter_id=reporter.id,
        title=title,
        description=f"Descripción de {title}",
        impact_level=ImpactLevel.MEDIUM,
    )
    ticket.created_at = datetime.now(UTC) - timedelta(hours=hours_ago)
    SqlAlchemyTicketRepository(context.session).save(ticket)
    context.query_tickets = getattr(context, "query_tickets", {})
    context.query_tickets[title] = ticket
    return ticket


@given("the collaborator has reported {count:d} tickets")
def step_reported_tickets(context, count):
    # "Incidente N" es el más reciente
    for i in range(1, count + 1):
        _report(context, context.users["COLLABORATOR"], f"Incidente {i}", hours_ago=count - i + 1)


@given('the other collaborator has reported a ticket titled "{title}"')
def step_other_reported(context, title):
    _report(context, context.other_collaborator, title, hours_ago=0)


@when('the "{role}" requests their ticket history page {page:d} with {size:d} tickets per page')
def step_history_page(context, role, page, size):
    context.response = context.client.get(
        f"{HISTORY_URL}?page={page}&size={size}", headers=_headers_for(context, context.users[role])
    )


@when('the "{role}" requests their ticket history with "{query}"')
def step_history_query(context, role, query):
    context.response = context.client.get(f"{HISTORY_URL}?{query}", headers=_headers_for(context, context.users[role]))


@when("the other collaborator requests their ticket history")
def step_other_history(context):
    context.response = context.client.get(HISTORY_URL, headers=_headers_for(context, context.other_collaborator))


@when('the "{role}" opens the detail of the ticket "{title}"')
def step_open_detail(context, role, title):
    ticket = context.query_tickets[title]
    context.response = context.client.get(
        f"/api/v1/tickets/{ticket.id}", headers=_headers_for(context, context.users[role])
    )


@when('the other collaborator opens the detail of the ticket "{title}"')
def step_other_opens_detail(context, title):
    ticket = context.query_tickets[title]
    context.response = context.client.get(
        f"/api/v1/tickets/{ticket.id}", headers=_headers_for(context, context.other_collaborator)
    )


@when('the "{role}" opens the detail of a nonexistent ticket')
def step_open_unknown(context, role):
    context.response = context.client.get(
        f"/api/v1/tickets/{uuid.uuid4()}", headers=_headers_for(context, context.users[role])
    )


@then("the page shows these tickets:")
def step_page_tickets(context):
    expected = [row["title"] for row in context.table]
    actual = [t["title"] for t in context.response.json()["items"]]
    assert actual == expected, f"Se esperaba {expected} y la página muestra {actual}"


@then("the pagination shows page {page:d} of {pages:d} with {total:d} tickets")
def step_pagination(context, page, pages, total):
    body = context.response.json()
    assert (body["page"], body["total_pages"], body["total"]) == (page, pages, total), body


@then('the page does not show the ticket "{title}"')
def step_page_without(context, title):
    assert title not in [t["title"] for t in context.response.json()["items"]]


@then("the page is empty")
def step_page_empty(context):
    body = context.response.json()
    assert body["items"] == [] and body["total"] == 0 and body["total_pages"] == 0, body


@then('the detail shows the ticket "{title}" reported by the collaborator')
def step_detail(context, title):
    body = context.response.json()
    ticket = context.query_tickets[title]
    assert body["code"] == ticket.code and body["title"] == title
    assert body["description"] == f"Descripción de {title}"
    assert body["reporter_name"] == context.users["COLLABORATOR"].full_name


@then("the error is reported as problem details")
def step_problem_details(context):
    assert context.response.headers["content-type"].startswith("application/problem+json"), context.response.headers
    body = context.response.json()
    assert body["status"] == context.response.status_code and body["detail"], body
