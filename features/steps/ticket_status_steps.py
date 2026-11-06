"""Steps de la feature de la máquina de estados del ticket (T15, TS04)."""
import uuid

from behave import given, then, when

from app.helpdesk.domain import state_machine
from app.helpdesk.domain.enums import ImpactLevel, SupportTier, TicketStatus
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.models import TicketModel
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider

FAKE_HASH = "$2b$04$abcdefghijklmnopqrstuuJ8Pn6R6qVqzLqL7vR0Qe2b7r6P9q5Gm"


@given("a workspace with users for every role")
def step_workspace_users(context):
    workspace = WorkspaceModel(id=uuid.uuid4(), name="Empresa Demo", subdomain=f"demo-{uuid.uuid4().hex[:6]}")
    context.session.add(workspace)
    context.session.flush()
    context.users = {}
    for role in RoleName:
        user = UserModel(
            id=uuid.uuid4(), workspace_id=workspace.id, full_name=f"{role.value} Demo",
            email=f"{role.value.lower()}-{uuid.uuid4().hex[:6]}@demo.pe", password_hash=FAKE_HASH,
            role=role, department="TI",
        )
        context.session.add(user)
        context.users[role.value] = user
    context.session.flush()
    context.workspace = workspace


@given("a ticket reported by the collaborator")
def step_ticket(context):
    ticket = Ticket.register(
        workspace_id=context.workspace.id,
        reporter_id=context.users["COLLABORATOR"].id,
        title="No puedo ingresar al ERP",
        description="Error 0x80070005 al iniciar sesión",
        impact_level=ImpactLevel.MEDIUM,
    )
    SqlAlchemyTicketRepository(context.session).save(ticket)
    context.ticket_id = ticket.id


@given('the ticket is in status "{status}"')
def step_ticket_in_status(context, status):
    # Se fija el estado directamente para preparar el escenario sin recorrer todo el ciclo
    model = context.session.get(TicketModel, context.ticket_id)
    model.status = TicketStatus(status)
    model.current_tier = state_machine.TIER_BY_STATUS.get(model.status, SupportTier.TIER_L1)
    if model.status in {TicketStatus.ASSIGNED_L1, TicketStatus.ESCALATED_L2, TicketStatus.RESOLVED}:
        model.assigned_analyst_id = context.users["ANALYST_L1"].id
    context.session.flush()


@when('the "{role}" changes the ticket status to "{status}"')
def step_change_status(context, role, status):
    user = SqlAlchemyUserRepository(context.session).find_by_id(context.users[role].id)
    token, _ = get_token_provider().issue_access_token(user)
    context.response = context.client.patch(
        f"/api/v1/tickets/{context.ticket_id}/status",
        json={"status": status},
        headers={"Authorization": f"Bearer {token}"},
    )


@then('the ticket status is "{status}"')
def step_ticket_status(context, status):
    context.session.expire_all()
    assert context.session.get(TicketModel, context.ticket_id).status.value == status


@then('the ticket is assigned to the "{role}"')
def step_ticket_assigned(context, role):
    context.session.expire_all()
    assert context.session.get(TicketModel, context.ticket_id).assigned_analyst_id == context.users[role].id


def _token_for(context, user_model) -> str:
    user = SqlAlchemyUserRepository(context.session).find_by_id(user_model.id)
    token, _ = get_token_provider().issue_access_token(user)
    return token


@given("another collaborator in the same workspace")
def step_other_collaborator(context):
    other = UserModel(
        id=uuid.uuid4(), workspace_id=context.workspace.id, full_name="Otro Colaborador",
        email=f"otro-{uuid.uuid4().hex[:6]}@demo.pe", password_hash=FAKE_HASH,
        role=RoleName.COLLABORATOR, department="Ventas",
    )
    context.session.add(other)
    context.session.flush()
    context.other_collaborator = other


@when('the other collaborator changes the ticket status to "{status}"')
def step_other_changes_status(context, status):
    context.response = context.client.patch(
        f"/api/v1/tickets/{context.ticket_id}/status",
        json={"status": status},
        headers={"Authorization": f"Bearer {_token_for(context, context.other_collaborator)}"},
    )


@when('the "{role}" changes the status of a nonexistent ticket to "{status}"')
def step_change_unknown_ticket(context, role, status):
    context.response = context.client.patch(
        f"/api/v1/tickets/{uuid.uuid4()}/status",
        json={"status": status},
        headers={"Authorization": f"Bearer {_token_for(context, context.users[role])}"},
    )


@then('the response shows the ticket in status "{status}"')
def step_response_ticket_status(context, status):
    body = context.response.json()
    assert body["id"] == str(context.ticket_id), body
    assert body["status"] == status, body


@then("the response shows the resolution date")
def step_response_resolved_at(context):
    assert context.response.json()["resolved_at"] is not None


@then('the status history records the transition from "{previous}" to "{target}" by the "{role}"')
def step_status_history_recorded(context, previous, target, role):
    history = context.response.json().get("status_history", [])
    assert len(history) >= 1, f"Se esperaba historial de estados y se obtuvo: {history}"
    last = history[-1]
    assert last["previous_status"] == previous
    assert last["new_status"] == target
    assert last["changed_by"] == str(context.users[role].id)
    assert last["changed_at"] is not None

