"""Steps de la feature de la bandeja del analista (T49, US24)."""
import uuid
from datetime import UTC, datetime, timedelta

from behave import given, then, when

from app.helpdesk.domain.enums import ImpactLevel, TicketPriority, TicketStatus
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider

QUEUE_URL = "/api/v1/tickets/queue"
FAKE_HASH = "$2b$04$abcdefghijklmnopqrstuuJ8Pn6R6qVqzLqL7vR0Qe2b7r6P9q5Gm"


def _user(context, name: str) -> UserModel:
    """Usuario por rol; OTHER_ANALYST es un segundo analista L1 que se crea al pedirlo."""
    if name not in context.users and name == "OTHER_ANALYST":
        user = UserModel(
            id=uuid.uuid4(), workspace_id=context.workspace.id, full_name="Otra Analista",
            email=f"otra-analista-{uuid.uuid4().hex[:6]}@demo.pe", password_hash=FAKE_HASH,
            role=RoleName.ANALYST_L1, department="Mesa de Ayuda",
        )
        context.session.add(user)
        context.session.flush()
        context.users[name] = user
    return context.users[name]


def _headers(context, name: str) -> dict:
    user = SqlAlchemyUserRepository(context.session).find_by_id(_user(context, name).id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _items(context) -> list[dict]:
    assert context.response.status_code == 200, context.response.text
    return context.response.json()["items"]


@given("these tickets in the workspace:")
def step_tickets(context):
    repo = SqlAlchemyTicketRepository(context.session)
    now = datetime.now(UTC)
    context.tickets = {}
    for row in context.table:
        ticket = Ticket.register(
            workspace_id=context.workspace.id,
            reporter_id=context.users["COLLABORATOR"].id,
            title=row["title"].strip(),
            description="Incidente de prueba de la bandeja",
            impact_level=ImpactLevel.MEDIUM,
        )
        ticket.priority = TicketPriority(row["priority"])
        ticket.status = TicketStatus(row["status"])
        assigned = row["assigned_to"].strip()
        ticket.assigned_analyst_id = _user(context, assigned).id if assigned else None
        ticket.created_at = now - timedelta(hours=int(row["hours_ago"]))
        repo.save(ticket)
        context.tickets[ticket.title] = ticket


@when('the "{name}" opens the "{scope}" queue')
def step_open_queue(context, name, scope):
    context.response = context.client.get(f"{QUEUE_URL}?scope={scope}", headers=_headers(context, name))


@when('the "{name}" opens the "{scope}" queue with "{filters}"')
def step_open_filtered_queue(context, name, scope, filters):
    context.response = context.client.get(f"{QUEUE_URL}?scope={scope}&{filters}", headers=_headers(context, name))


@when('the "{name}" attends the ticket "{title}"')
def step_attend(context, name, title):
    ticket = context.tickets[title]
    context.response = context.client.patch(
        f"/api/v1/tickets/{ticket.id}/status",
        json={"status": "ASSIGNED_L1", "reason": "Tomado desde la Mesa de ayuda"},
        headers=_headers(context, name),
    )
    assert context.response.status_code == 200, context.response.text


@then("the queue shows these tickets in order:")
def step_queue_order(context):
    expected = [row["title"].strip() for row in context.table if row["title"].strip()]
    actual = [t["title"] for t in _items(context)]
    assert actual == expected, f"Se esperaba {expected} y la bandeja muestra {actual}"
    assert context.response.json()["total"] == len(expected)


@then("the queue is empty")
def step_queue_empty(context):
    body = context.response.json()
    assert _items(context) == [] and body["total"] == 0, body


@then("each ticket in the queue shows who reported it")
def step_reporter_names(context):
    expected = context.users["COLLABORATOR"].full_name
    assert all(t["reporter_name"] == expected for t in _items(context)), _items(context)


@then('the queue does not show the ticket "{title}"')
def step_ticket_absent(context, title):
    assert title not in [t["title"] for t in _items(context)]


@then('the queue shows the ticket "{title}" assigned to the "{name}"')
def step_ticket_assigned(context, title, name):
    match = [t for t in _items(context) if t["title"] == title]
    assert match, f'"{title}" no aparece en la bandeja'
    assert match[0]["assigned_analyst_id"] == str(_user(context, name).id)
    assert match[0]["status"] == "ASSIGNED_L1"


@when('the "{name}" changes their availability to "{availability}"')
def step_change_availability(context, name, availability):
    context.response = context.client.patch(
        "/api/v1/analysts/me/availability",
        json={"availability_status": availability},
        headers=_headers(context, name),
    )


@then('the "{name}" appears as "{availability}"')
def step_analyst_appears_as(context, name, availability):
    assert context.response.status_code == 200, context.response.text
    assert context.response.json()["availability_status"] == availability
    analysts_resp = context.client.get("/api/v1/analysts", headers=_headers(context, name))
    assert analysts_resp.status_code == 200, analysts_resp.text
    target_id = str(_user(context, name).id)
    found = [a for a in analysts_resp.json() if a["id"] == target_id]
    assert found and found[0]["availability_status"] == availability, found
